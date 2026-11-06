"""下载有序来源，编排分段合成并写出成片清单。"""

from __future__ import annotations

from pathlib import Path
from typing import Callable

from download_video import DownloadError, download, extract_urls

from .._constants import MAX_PART_SECONDS, SEGMENTATION_DURATION, SEGMENTATION_EPISODES
from .._errors import AnimeError

from .ffmpeg import Progress, probe_video, report_progress
from .media_artifacts import write_json, write_text
from .segmentation import part_ranges, split_ranges
from .video_rendering import render_video_part


def normalize_share_texts(share_texts: list[str] | str) -> list[str]:
    """整理成有序链接。一条文字里有多条链接时按出现顺序拆开。"""
    if isinstance(share_texts, str):
        raw_items = [share_texts]
    elif isinstance(share_texts, list):
        raw_items = [str(item) for item in share_texts]
    else:
        raise AnimeError("share_texts 必须是链接列表")

    items: list[str] = []
    for raw in raw_items:
        text = raw.strip()
        if not text:
            continue
        urls = extract_urls(text)
        if len(urls) <= 1:
            items.append(text)
        else:
            items.extend(urls)
    if not items:
        raise AnimeError("至少提供一条视频链接")
    return items


def compile_videos(
    share_texts: list[str],
    output_dir: Path,
    progress: Progress | None = None,
) -> dict:
    """下载全部分享链接，再按顺序拼接并写出每段文案。"""
    output_dir = Path(output_dir)
    output_dir.mkdir(parents=True, exist_ok=True)
    source_dir = output_dir / "sources"
    source_dir.mkdir(parents=True, exist_ok=True)
    total = len(share_texts)
    sources: list[dict] = []

    for index, share_text in enumerate(share_texts, start=1):
        report_progress(progress, f"正在解析并下载第 {index}/{total} 条")
        destination = source_dir / f"{index:02d}.mp4"
        try:
            resolved = download(share_text, destination)
        except DownloadError as exc:
            preview = share_text.replace("\n", " ")[:80]
            raise AnimeError(f"第 {index} 条链接失败：{exc.message}（{preview}）") from exc
        probe = probe_video(destination)
        record = {
            "order": index,
            "path": destination,
            "duration": probe["duration"],
            "probe": probe,
            "platform": resolved.get("platform") or "",
            "video_id": resolved.get("video_id") or "",
            "share_text": share_text,
            "title": (resolved.get("title") or "").strip(),
            "description": (resolved.get("description") or "").strip(),
            "topics": [str(item) for item in (resolved.get("topics") or []) if str(item).strip()],
        }
        write_json(source_dir / f"{index:02d}.json", _source_payload(record))
        sources.append(record)

    return assemble_videos(sources, output_dir, progress=progress)


def assemble_videos(
    sources: list[dict],
    output_dir: Path,
    *,
    max_part_seconds: float = MAX_PART_SECONDS,
    progress: Progress | None = None,
    part_ready: Callable[[dict], None] | None = None,
    completed_parts: dict[int, dict] | None = None,
    segmentation: str = SEGMENTATION_EPISODES,
) -> dict:
    """按完整剧集边界均衡拼接，或按时间线均分长视频；每段完成后立即持久化或发布。"""
    if not sources:
        raise AnimeError("没有可拼接的视频")
    output_dir = Path(output_dir)
    output_dir.mkdir(parents=True, exist_ok=True)
    total_seconds = 0.0
    timeline: list[dict] = []
    for source in sources:
        path = Path(source["path"])
        probe = source.get("probe") or probe_video(path)
        duration = float(probe["duration"])
        if duration <= 0:
            raise AnimeError(f"第 {source.get('order', '?')} 条视频时长无效")
        timeline.append({
            **source,
            "path": path,
            "probe": probe,
            "duration": duration,
            "offset": total_seconds,
        })
        total_seconds += duration

    if segmentation == SEGMENTATION_DURATION:
        ranges = split_ranges(total_seconds, max_part_seconds)
    else:
        episode_durations = []
        episode_seconds = 0.0
        for source in timeline:
            episode_seconds += source["duration"]
            if source.get("episode_boundary_after", True):
                episode_durations.append(episode_seconds)
                episode_seconds = 0.0
        if episode_seconds:
            raise AnimeError("检查点缺少完整剧集结束边界，不能按时间硬切")
        ranges = part_ranges(episode_durations, max_part_seconds)
    parts: list[dict] = []
    width = len(str(len(ranges)))
    completed_parts = completed_parts or {}
    for index, (start, end) in enumerate(ranges, start=1):
        clips = _clips_for_range(timeline, start, end)
        if not clips:
            raise AnimeError(f"第 {index} 段没有可拼接的画面")
        video_path = output_dir / f"part-{index:0{width}d}.mp4"
        resumed = index in completed_parts
        if resumed:
            report_progress(progress, f"根据 YouTube 回执跳过第 {index}/{len(ranges)} 段")
            actual = {"duration": end - start}
        else:
            report_progress(progress, f"正在拼接第 {index}/{len(ranges)} 段")
            render_video_part(clips, video_path, progress=progress, label=f"第 {index}/{len(ranges)} 段",
                         segmentation=segmentation)
            actual = probe_video(video_path)
        included = _sources_for_range(timeline, start, end)
        metadata = _combine_metadata(included)
        payload = {
            "part_index": index,
            "part_count": len(ranges),
            "video_path": str(video_path),
            "duration_seconds": round(actual["duration"], 3),
            "timeline_start_seconds": round(start, 3),
            "timeline_end_seconds": round(end, 3),
            **metadata,
            "sources": included,
        }
        if resumed:
            payload["sha256"] = completed_parts[index]["sha256"]
        metadata_path = video_path.with_suffix(".json")
        write_json(metadata_path, payload)
        write_text(video_path.with_suffix(".txt"), _metadata_text(payload))
        parts.append({**payload, "metadata_path": str(metadata_path)})
        if part_ready and not resumed:
            partial_manifest = {
                "output_dir": str(output_dir.resolve()),
                "total_duration_seconds": round(total_seconds, 3),
                "part_count": len(ranges),
                "max_part_seconds": max_part_seconds,
                "parts": parts,
            }
            write_json(output_dir / "manifest.json", partial_manifest)
            part_ready(partial_manifest)

    manifest = {
        "output_dir": str(output_dir.resolve()),
        "total_duration_seconds": round(total_seconds, 3),
        "part_count": len(parts),
        "max_part_seconds": max_part_seconds,
        "parts": parts,
    }
    write_json(output_dir / "manifest.json", manifest)
    report_progress(progress, "拼接完成")
    return manifest


def _clips_for_range(timeline: list[dict], start: float, end: float) -> list[dict]:
    clips: list[dict] = []
    for source in timeline:
        offset = float(source["offset"])
        duration = float(source["duration"])
        source_end = offset + duration
        overlap_start = max(start, offset)
        overlap_end = min(end, source_end)
        if overlap_end - overlap_start <= 0.001:
            continue
        local_start = overlap_start - offset
        local_end = overlap_end - offset
        clip_start = 0.0 if local_start <= 0.05 else local_start
        clip_end = duration if duration - local_end <= 0.05 else local_end
        clips.append({
            "path": Path(source["path"]),
            "probe": source["probe"],
            "start": clip_start,
            "duration": max(clip_end - clip_start, 0.001),
            "full": clip_start <= 0.05 and duration - clip_end <= 0.05,
        })
    return clips


def _sources_for_range(timeline: list[dict], start: float, end: float) -> list[dict]:
    included: list[dict] = []
    for source in timeline:
        offset = float(source["offset"])
        duration = float(source["duration"])
        source_end = offset + duration
        overlap_start = max(start, offset)
        overlap_end = min(end, source_end)
        if overlap_end - overlap_start <= 0.001:
            continue
        included.append({
            "order": source.get("order"),
            "platform": source.get("platform") or "",
            "video_id": source.get("video_id") or "",
            "share_text": source.get("share_text") or "",
            "source_path": str(Path(source["path"]).resolve()),
            "title": source.get("title") or "",
            "description": source.get("description") or "",
            "topics": list(source.get("topics") or []),
            "included_start_seconds": round(max(0.0, overlap_start - offset), 3),
            "included_end_seconds": round(min(duration, overlap_end - offset), 3),
        })
    return included


def _combine_metadata(sources: list[dict]) -> dict:
    """按来源顺序原样拼接文案，不改写用词。"""
    titles: list[str] = []
    descriptions: list[str] = []
    topics: list[str] = []
    seen_topics: set[str] = set()
    for source in sources:
        title = str(source.get("title") or "").strip()
        if title:
            titles.append(title)
        description = str(source.get("description") or "").strip()
        if description:
            descriptions.append(description)
        for topic in source.get("topics") or []:
            text = str(topic).strip()
            if text and text not in seen_topics:
                seen_topics.add(text)
                topics.append(text)
    return {
        "title": "\n".join(titles) or "未命名视频",
        "description": "\n\n".join(descriptions),
        "topics": topics,
    }


def _metadata_text(payload: dict) -> str:
    topics = " ".join(payload.get("topics") or [])
    return (
        f"第 {payload['part_index']} 段 / 共 {payload['part_count']} 段\n\n"
        f"标题：\n{payload.get('title') or ''}\n\n"
        f"描述：\n{payload.get('description') or ''}\n\n"
        f"话题：\n{topics}\n"
    )


def _source_payload(record: dict) -> dict:
    return {
        "order": record["order"],
        "platform": record["platform"],
        "video_id": record["video_id"],
        "share_text": record["share_text"],
        "video_path": str(Path(record["path"]).resolve()),
        "duration_seconds": round(float(record["duration"]), 3),
        "title": record["title"],
        "description": record["description"],
        "topics": record["topics"],
    }
