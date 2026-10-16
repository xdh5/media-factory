"""按顺序下载分享链接，均分拼接成每段最长 3 小时的本地视频。"""

from __future__ import annotations

import json
import math
import os
import re
import shutil
import subprocess
import sys
import threading
import time
import tempfile
from pathlib import Path
from typing import Callable

from download_video import DownloadError, download, extract_urls

from .._constants import MAX_PART_SECONDS
from .._errors import AnimeError

Progress = Callable[[str], None]

_TIME_RE = re.compile(r"(\d+):(\d+):(\d+(?:\.\d+)?)")


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


def part_count(total_seconds: float, max_part_seconds: float = MAX_PART_SECONDS) -> int:
    """按单段上限计算段数。刚好落在 3、6、9 小时边界时不额外多切一段。"""
    if total_seconds <= 0:
        raise AnimeError("视频总时长无效")
    if max_part_seconds <= 0:
        raise AnimeError("单段时长上限无效")
    return max(1, math.ceil((total_seconds - 0.05) / max_part_seconds))


def part_ranges(
    total_seconds: float,
    max_part_seconds: float = MAX_PART_SECONDS,
) -> list[tuple[float, float]]:
    """把总时长均分成若干段，每段都不超过上限。"""
    count = part_count(total_seconds, max_part_seconds)
    span = total_seconds / count
    ranges: list[tuple[float, float]] = []
    for index in range(count):
        start = 0.0 if index == 0 else span * index
        end = total_seconds if index == count - 1 else span * (index + 1)
        ranges.append((start, end))
    return ranges


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
        _report(progress, f"正在解析并下载第 {index}/{total} 条")
        destination = source_dir / f"{index:02d}.mp4"
        try:
            resolved = download(share_text, destination)
        except DownloadError as exc:
            preview = share_text.replace("\n", " ")[:80]
            raise AnimeError(f"第 {index} 条链接失败：{exc.message}（{preview}）") from exc
        probe = _probe(destination)
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
        _write_json(source_dir / f"{index:02d}.json", _source_payload(record))
        sources.append(record)

    return assemble_videos(sources, output_dir, progress=progress)


def assemble_videos(
    sources: list[dict],
    output_dir: Path,
    *,
    max_part_seconds: float = MAX_PART_SECONDS,
    progress: Progress | None = None,
    part_ready: Callable[[dict], None] | None = None,
) -> dict:
    """把来源按顺序均分拼接；每段完成后可立即交给调用方持久化或发布。"""
    if not sources:
        raise AnimeError("没有可拼接的视频")
    output_dir = Path(output_dir)
    output_dir.mkdir(parents=True, exist_ok=True)
    total_seconds = 0.0
    timeline: list[dict] = []
    for source in sources:
        path = Path(source["path"])
        probe = source.get("probe") or _probe(path)
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

    ranges = part_ranges(total_seconds, max_part_seconds)
    parts: list[dict] = []
    width = len(str(len(ranges)))
    for index, (start, end) in enumerate(ranges, start=1):
        _report(progress, f"正在拼接第 {index}/{len(ranges)} 段")
        clips = _clips_for_range(timeline, start, end)
        if not clips:
            raise AnimeError(f"第 {index} 段没有可拼接的画面")
        video_path = output_dir / f"part-{index:0{width}d}.mp4"
        _render_part(clips, video_path, progress=progress, label=f"第 {index}/{len(ranges)} 段")
        actual = _probe(video_path)
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
        metadata_path = video_path.with_suffix(".json")
        _write_json(metadata_path, payload)
        _write_text(video_path.with_suffix(".txt"), _metadata_text(payload))
        parts.append({**payload, "metadata_path": str(metadata_path)})
        if part_ready:
            partial_manifest = {
                "output_dir": str(output_dir.resolve()),
                "total_duration_seconds": round(total_seconds, 3),
                "part_count": len(ranges),
                "max_part_seconds": max_part_seconds,
                "parts": parts,
            }
            _write_json(output_dir / "manifest.json", partial_manifest)
            part_ready(partial_manifest)

    manifest = {
        "output_dir": str(output_dir.resolve()),
        "total_duration_seconds": round(total_seconds, 3),
        "part_count": len(parts),
        "max_part_seconds": max_part_seconds,
        "parts": parts,
    }
    _write_json(output_dir / "manifest.json", manifest)
    _report(progress, "拼接完成")
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


def _render_part(clips: list[dict], output_path: Path, *, progress: Progress | None, label: str) -> None:
    output_path.parent.mkdir(parents=True, exist_ok=True)
    temporary = output_path.with_name(f".{output_path.stem}.tmp.mp4")
    try:
        if len(clips) == 1 and clips[0]["full"]:
            shutil.copy2(clips[0]["path"], temporary)
        elif _can_stream_copy(clips):
            try:
                _concat_copy(clips, temporary)
            except AnimeError:
                _report(progress, f"{label} 直接拼接失败，改为重新编码")
                _concat_reencode(clips, temporary, progress=progress, label=label)
        elif clips and all(_signature(clip["probe"]) == _signature(clips[0]["probe"]) for clip in clips):
            try:
                _concat_trimmed_boundaries(clips, temporary, progress=progress, label=label)
            except AnimeError:
                _report(progress, f"{label} 边界处理后格式不一致，改为统一编码")
                _concat_reencode(clips, temporary, progress=progress, label=label)
        else:
            try:
                _report(progress, f"{label} 来源参数不一致，优先保留原始音画直接拼接")
                _concat_packet_copy(clips, temporary)
            except AnimeError:
                _report(progress, f"{label} 直接拼接失败，改为统一编码")
                _concat_reencode(clips, temporary, progress=progress, label=label)
        if not temporary.is_file() or temporary.stat().st_size <= 0:
            raise AnimeError(f"{label} 没有写出视频文件")
        os.replace(temporary, output_path)
    finally:
        temporary.unlink(missing_ok=True)


def _can_stream_copy(clips: list[dict]) -> bool:
    if not clips or any(not clip["full"] for clip in clips):
        return False
    first = _signature(clips[0]["probe"])
    return all(_signature(clip["probe"]) == first for clip in clips)


def _concat_trimmed_boundaries(clips, output_path, *, progress, label):
    """完整块直接复用，只编码分段边界涉及的小块，避免整段长视频重复编码。"""
    with tempfile.TemporaryDirectory(prefix=".boundary-", dir=output_path.parent) as temporary:
        prepared = []
        signature = _signature(clips[0]["probe"])
        for index, clip in enumerate(clips):
            if clip["full"]:
                prepared.append(clip)
                continue
            _report(progress, f"{label} 仅处理分段边界 {index + 1}/{len(clips)}")
            path = Path(temporary) / f"boundary-{index}.mp4"
            _concat_reencode([clip], path, progress=progress, label=label)
            probe = _probe(path)
            if _signature(probe) != signature or abs(probe["duration"] - clip["duration"]) > 0.5:
                raise AnimeError("边界视频的格式或时长不适合直接拼接")
            prepared.append({"path": path, "probe": probe, "duration": probe["duration"], "full": True})
        _concat_copy(prepared, output_path)
        expected = sum(clip["duration"] for clip in clips)
        if abs(_probe(output_path)["duration"] - expected) > max(0.5, len(clips) * 0.05):
            raise AnimeError("边界处理后的成片时长不符")


def _concat_packet_copy(clips: list[dict], output_path: Path) -> None:
    """不解码音视频；只对分段边界做关键帧裁切，再按原始数据包拼接。"""
    ffmpeg = _executable("ffmpeg")
    with tempfile.TemporaryDirectory(prefix=".packet-copy-", dir=output_path.parent) as temporary:
        prepared: list[dict] = []
        for index, clip in enumerate(clips):
            if clip["full"]:
                prepared.append(clip)
                continue
            path = Path(temporary) / f"boundary-{index}.mp4"
            command = [ffmpeg, "-y", "-hide_banner", "-loglevel", "error"]
            if clip["start"] > 0.05:
                command.extend(["-ss", f"{clip['start']:.3f}"])
            command.extend([
                "-i", str(clip["path"]), "-t", f"{clip['duration']:.3f}",
                "-map", "0:v:0", "-map", "0:a?", "-c", "copy",
                "-avoid_negative_ts", "make_zero", str(path),
            ])
            _run_ffmpeg(command, total_seconds=clip["duration"], progress=None, label="边界直接裁切")
            probe = _probe(path)
            prepared.append({"path": path, "probe": probe, "duration": probe["duration"], "full": True})
        _concat_copy(prepared, output_path)
        expected = sum(clip["duration"] for clip in clips)
        actual = _probe(output_path)["duration"]
        if abs(actual - expected) > max(3.0, len(clips) * 0.1):
            raise AnimeError("直接拼接后的成片时长不符")


def _signature(probe: dict) -> tuple:
    return (
        probe.get("width"),
        probe.get("height"),
        probe.get("vcodec"),
        probe.get("acodec"),
        probe.get("fps_token"),
        probe.get("pix_fmt"),
        probe.get("sample_rate"),
        probe.get("channels"),
    )


def _concat_copy(clips: list[dict], output_path: Path) -> None:
    ffmpeg = _executable("ffmpeg")
    script = output_path.with_name(f".{output_path.stem}.concat.txt")
    lines = []
    for clip in clips:
        escaped = clip["path"].resolve().as_posix().replace("'", r"'\''")
        lines.append(f"file '{escaped}'")
    script.write_text("\n".join(lines) + "\n", encoding="utf-8")
    command = [
        ffmpeg, "-y", "-hide_banner", "-loglevel", "error",
        "-f", "concat", "-safe", "0", "-i", str(script),
        "-c", "copy", "-movflags", "+faststart",
        str(output_path),
    ]
    try:
        _run_ffmpeg(command, total_seconds=sum(clip["duration"] for clip in clips), progress=None, label="直接拼接")
    finally:
        script.unlink(missing_ok=True)


def _concat_reencode(
    clips: list[dict],
    output_path: Path,
    *,
    progress: Progress | None,
    label: str,
) -> None:
    ffmpeg = _executable("ffmpeg")
    canvas = clips[0]["probe"]
    width = _even(int(canvas.get("width") or 0))
    height = _even(int(canvas.get("height") or 0))
    if width < 2 or height < 2:
        raise AnimeError("视频没有可用画面，无法拼接")
    fps_token = _shared_fps(clips)
    filters: list[str] = []
    command = [ffmpeg, "-y", "-hide_banner", "-loglevel", "error"]
    for index, clip in enumerate(clips):
        if clip["start"] > 0.05:
            command.extend(["-ss", f"{clip['start']:.3f}"])
        if not clip["full"]:
            command.extend(["-t", f"{clip['duration']:.3f}"])
        # 来源文件可能夹有少量损坏 AAC 包；保留可解码原声，仅跳过坏包。
        command.extend(["-fflags", "+discardcorrupt", "-err_detect", "ignore_err", "-i", str(clip["path"])])
        duration = f"{clip['duration']:.3f}"
        video_index = int(clip["probe"]["video_stream_index"])
        filters.append(
            f"[{index}:{video_index}]setpts=PTS-STARTPTS,"
            f"scale={width}:{height}:force_original_aspect_ratio=decrease,"
            f"pad={width}:{height}:(ow-iw)/2:(oh-ih)/2:color=black,"
            f"setsar=1,fps={fps_token},format=yuv420p,"
            f"trim=duration={duration},setpts=PTS-STARTPTS[v{index}]"
        )
        audio_index = clip["probe"].get("audio_stream_index")
        if audio_index is None:
            filters.append(
                f"anullsrc=channel_layout=stereo:sample_rate=48000,"
                f"atrim=duration={duration},asetpts=PTS-STARTPTS[a{index}]"
            )
        else:
            filters.append(
                f"[{index}:{int(audio_index)}]asetpts=PTS-STARTPTS,"
                f"aresample=48000:async=1:first_pts=0,aformat=sample_fmts=fltp:channel_layouts=stereo,"
                f"atrim=duration={duration},asetpts=PTS-STARTPTS,apad=whole_dur={duration}[a{index}]"
            )
    joined = "".join(f"[v{index}][a{index}]" for index in range(len(clips)))
    filters.append(f"{joined}concat=n={len(clips)}:v=1:a=1[vout][aout]")
    graph = ";".join(filters)
    command.extend([
        "-filter_complex", graph,
        "-map", "[vout]", "-map", "[aout]",
        "-c:v", "libx264", "-preset", "veryfast", "-crf", "20",
        "-r", fps_token, "-fps_mode", "cfr",
        "-c:a", "aac", "-b:a", "192k",
        "-movflags", "+faststart",
        "-progress", "pipe:1", "-nostats",
        str(output_path),
    ])
    total_seconds = sum(clip["duration"] for clip in clips)
    # Windows 命令行大约 3 万字符。超长时改成逐段编码再复制拼接。
    if sum(len(part) + 1 for part in command) > 28000:
        _concat_reencode_chunked(
            clips, output_path, width=width, height=height, fps_token=fps_token,
            progress=progress, label=label,
        )
        return
    _run_ffmpeg(command, total_seconds=total_seconds, progress=progress, label=label)


def _concat_reencode_chunked(
    clips: list[dict],
    output_path: Path,
    *,
    width: int,
    height: int,
    fps_token: str,
    progress: Progress | None,
    label: str,
) -> None:
    """滤镜图放不进命令行时，先把每条规范成相同参数，再复制拼接。"""
    ffmpeg = _executable("ffmpeg")
    temporary_dir = output_path.parent / f".{output_path.stem}-parts"
    temporary_dir.mkdir(parents=True, exist_ok=True)
    normalized: list[dict] = []
    try:
        for index, clip in enumerate(clips, start=1):
            _report(progress, f"正在编码{label}的第 {index}/{len(clips)} 条")
            target = temporary_dir / f"{index:03d}.mp4"
            duration = f"{clip['duration']:.3f}"
            command = [ffmpeg, "-y", "-hide_banner", "-loglevel", "error"]
            if clip["start"] > 0.05:
                command.extend(["-ss", f"{clip['start']:.3f}"])
            if not clip["full"]:
                command.extend(["-t", duration])
            # 与整段编码保持一致：只丢弃损坏包，不静音整条来源。
            command.extend(["-fflags", "+discardcorrupt", "-err_detect", "ignore_err", "-i", str(clip["path"])])
            video_index = int(clip["probe"]["video_stream_index"])
            video_filter = (
                f"[0:{video_index}]setpts=PTS-STARTPTS,"
                f"scale={width}:{height}:force_original_aspect_ratio=decrease,"
                f"pad={width}:{height}:(ow-iw)/2:(oh-ih)/2:color=black,"
                f"setsar=1,fps={fps_token},format=yuv420p,"
                f"trim=duration={duration},setpts=PTS-STARTPTS[vout]"
            )
            audio_index = clip["probe"].get("audio_stream_index")
            if audio_index is None:
                audio_filter = (
                    f"anullsrc=channel_layout=stereo:sample_rate=48000,"
                    f"atrim=duration={duration},asetpts=PTS-STARTPTS[aout]"
                )
            else:
                audio_filter = (
                    f"[0:{int(audio_index)}]asetpts=PTS-STARTPTS,"
                    f"aresample=48000:async=1:first_pts=0,aformat=sample_fmts=fltp:channel_layouts=stereo,"
                    f"atrim=duration={duration},asetpts=PTS-STARTPTS,apad=whole_dur={duration}[aout]"
                )
            command.extend([
                "-filter_complex", f"{video_filter};{audio_filter}",
                "-map", "[vout]", "-map", "[aout]",
                "-c:v", "libx264", "-preset", "veryfast", "-crf", "20",
                "-c:a", "aac", "-b:a", "192k",
                "-progress", "pipe:1", "-nostats",
                str(target),
            ])
            _run_ffmpeg(command, total_seconds=clip["duration"], progress=progress, label=label)
            normalized.append({"path": target, "duration": clip["duration"], "full": True})
        _concat_copy(normalized, output_path)
    finally:
        shutil.rmtree(temporary_dir, ignore_errors=True)


def _shared_fps(clips: list[dict]) -> str:
    tokens = [str(clip["probe"].get("fps_token") or "") for clip in clips]
    first = tokens[0]
    if first and first not in {"0/0", "0"} and all(token == first for token in tokens):
        return first
    return "30"


def _run_ffmpeg(
    command: list[str],
    *,
    total_seconds: float,
    progress: Progress | None,
    label: str,
) -> None:
    log_path = Path(command[-1]).with_suffix(".ffmpeg.log")
    timeout = max(600.0, total_seconds * 8 + 120.0)
    kwargs = _subprocess_kwargs()
    with log_path.open("w", encoding="utf-8", errors="replace") as log_file:
        process = subprocess.Popen(
            command,
            stdout=subprocess.PIPE,
            stderr=log_file,
            text=True,
            encoding="utf-8",
            errors="replace",
            **kwargs,
        )
        last_report = 0.0

        def _read_progress() -> None:
            nonlocal last_report
            assert process.stdout is not None
            for line in process.stdout:
                timestamp = _parse_progress_time(line)
                if timestamp is None or progress is None or total_seconds <= 0:
                    continue
                now = time.monotonic()
                if now - last_report < 5:
                    continue
                last_report = now
                percent = min(99, max(0, int(timestamp / total_seconds * 100)))
                _report(progress, f"正在编码{label}（约 {percent}%）")

        reader = threading.Thread(target=_read_progress, daemon=True)
        reader.start()
        try:
            return_code = process.wait(timeout=timeout)
        except subprocess.TimeoutExpired as exc:
            process.kill()
            process.wait(timeout=30)
            raise AnimeError(f"{label} 编码超过 {int(timeout)} 秒") from exc
        reader.join(timeout=5)
    if return_code != 0:
        detail = ""
        if log_path.is_file():
            detail = log_path.read_text(encoding="utf-8", errors="replace").strip()[-1500:]
        raise AnimeError(f"{label} 拼接失败：{detail or 'ffmpeg 没有写出文件'}")
    log_path.unlink(missing_ok=True)


def _parse_progress_time(line: str) -> float | None:
    text = line.strip()
    if text.startswith("out_time_us="):
        try:
            return int(text.split("=", 1)[1]) / 1_000_000
        except ValueError:
            return None
    if text.startswith("out_time_ms=") and not text.startswith("out_time_ms=N/A"):
        # 新版 ffmpeg 的 out_time_ms 实际是微秒。
        try:
            return int(text.split("=", 1)[1]) / 1_000_000
        except ValueError:
            return None
    if text.startswith("out_time="):
        matched = _TIME_RE.search(text.split("=", 1)[1])
        if not matched:
            return None
        hours, minutes, seconds = matched.groups()
        return int(hours) * 3600 + int(minutes) * 60 + float(seconds)
    return None


def _probe(path: Path) -> dict:
    ffprobe = _executable("ffprobe")
    command = [
        ffprobe, "-v", "error",
        "-show_entries",
        "format=duration:stream=index,codec_type,codec_name,width,height,avg_frame_rate,pix_fmt,sample_rate,channels,disposition",
        "-of", "json",
        str(path),
    ]
    try:
        completed = subprocess.run(
            command,
            check=False,
            capture_output=True,
            text=True,
            encoding="utf-8",
            errors="replace",
            timeout=60,
            **_subprocess_kwargs(),
        )
    except subprocess.TimeoutExpired as exc:
        raise AnimeError(f"读取视频信息超时：{path.name}") from exc
    try:
        payload = json.loads(completed.stdout or "{}")
    except json.JSONDecodeError as exc:
        raise AnimeError(f"无法读取视频信息：{path.name}") from exc
    duration = float((payload.get("format") or {}).get("duration") or 0)
    if completed.returncode != 0 or duration <= 0:
        detail = (completed.stderr or "").strip()[-800:]
        raise AnimeError(f"无法读取视频时长：{path.name}。{detail}")
    streams = payload.get("streams") or []
    videos = [
        stream for stream in streams
        if stream.get("codec_type") == "video"
        and not int((stream.get("disposition") or {}).get("attached_pic") or 0)
    ]
    audios = [stream for stream in streams if stream.get("codec_type") == "audio"]
    if not videos:
        raise AnimeError(f"文件里没有画面：{path.name}")
    video = videos[0]
    audio = audios[0] if audios else None
    width = int(video.get("width") or 0)
    height = int(video.get("height") or 0)
    return {
        "duration": duration,
        "width": width,
        "height": height,
        "vcodec": video.get("codec_name") or "",
        "pix_fmt": video.get("pix_fmt") or "",
        "fps_token": str(video.get("avg_frame_rate") or ""),
        "video_stream_index": int(video.get("index") or 0),
        "acodec": (audio or {}).get("codec_name") or "",
        "sample_rate": str((audio or {}).get("sample_rate") or ""),
        "channels": int((audio or {}).get("channels") or 0),
        "audio_stream_index": None if audio is None else int(audio.get("index") or 0),
    }


def _executable(name: str) -> str:
    executable = shutil.which(name)
    if not executable:
        raise AnimeError(f"未找到 {name}，请确认已安装并加入 PATH")
    return executable


def _even(value: int) -> int:
    if value < 2:
        return 0
    return value if value % 2 == 0 else value + 1


def _subprocess_kwargs() -> dict:
    if sys.platform == "win32":
        return {"creationflags": subprocess.CREATE_NO_WINDOW}
    return {}


def _report(progress: Progress | None, message: str) -> None:
    if progress is not None:
        progress(message)


def _write_json(path: Path, payload: dict) -> None:
    path.write_text(json.dumps(payload, ensure_ascii=False, indent=2), encoding="utf-8")


def _write_text(path: Path, text: str) -> None:
    path.write_text(text, encoding="utf-8")
