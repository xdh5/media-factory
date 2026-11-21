"""冻结动漫发布来源并准备开头转写。"""

from __future__ import annotations

import time


from download_video._extractor import parse_share_text

from .._constants import OUTPUT_ROOT, SEGMENTATION_DURATION
from .._errors import AnimeError
from .compile import normalize_share_texts
from .media_artifacts import write_json
from .segmentation import split_ranges
from .discover import load_discovery
from .preview import extract_remote_preview, probe_remote_duration
from .youtube_assets import transcribe_intros

def prepare_execution(discovery_path: str, work_ids: list[str], selection_reason: str, progress) -> dict:
    """冻结选片顺序，只截取第一来源开头一分钟并转写。"""
    directory, discovery = load_discovery(discovery_path)
    works = {item["aweme_id"]: item for item in discovery["works"]}
    if not work_ids or len(set(work_ids)) != len(work_ids) or any(item not in works for item in work_ids):
        raise AnimeError("请选择发现记录中的不重复作品 ID，按最终播放顺序传入")
    if not selection_reason.strip():
        raise AnimeError("必须说明匹配、顺序、合集覆盖、去重、缺集和完结状态")
    if "已完结" not in selection_reason:
        raise AnimeError("发布执行清单必须明确说明作品已完结；仍在更新或证据不足时不能进入发布流程")
    selected = [works[item] for item in work_ids]
    if any(float(item.get("duration_seconds") or 0) <= 0 for item in selected):
        raise AnimeError("来源缺少有效时长，无法冻结执行清单")
    output = directory / f"execution-{time.time_ns()}"
    output.mkdir()
    write_json(output / "selection.json", {
        "series_name": discovery["series_name"], "profile_url": discovery["profile_url"],
        "selection_reason": selection_reason, "sources": selected,
    })
    progress("只读取第一来源开头一分钟，其他完整来源留给 Action 下载")
    preview = output / "preview.mp4"
    probe = extract_remote_preview(selected[0], preview)
    manifest = output / "manifest.json"
    write_json(manifest, {"preview_only": True, "parts": [{
        "part_index": 1, "video_path": str(preview), "duration_seconds": probe["duration"],
        "title": selected[0].get("title") or "",
    }]})
    result = transcribe_intros(str(manifest), progress)
    return {**result, "preview_only": True, "selection_path": str(output / "selection.json"),
            "source_count": len(selected),
            "next_step": "生成含已完结的一套文案，再以此 manifest_path 按预计分段数准备并保存对应封面"}


def prepare_split_execution(share_texts: list[str], series_name: str, selection_reason: str, progress) -> dict:
    """冻结用户直发长视频的来源顺序，只远程读取开头一分钟，由 Action 下载后按时间线拆分。"""
    texts = normalize_share_texts(share_texts)
    name = series_name.strip()
    if not name:
        raise AnimeError("必须提供作品名，用作 YouTube 播放列表和文案依据")
    if not selection_reason.strip():
        raise AnimeError("必须说明来源顺序、拆分依据和完结状态")
    if "已完结" not in selection_reason:
        raise AnimeError("发布执行清单必须明确说明作品已完结")
    output = OUTPUT_ROOT / f"split-{time.time_ns()}"
    output.mkdir(parents=True)
    sources = []
    for index, text in enumerate(texts, 1):
        progress(f"正在解析第 {index}/{len(texts)} 条来源，不下载整部视频")
        resolved = parse_share_text(text)
        if not resolved.video_id:
            raise AnimeError(f"第 {index} 条链接没有解析出视频 ID")
        sources.append({
            "order": index,
            "aweme_id": resolved.video_id,
            "work_url": text,
            "title": resolved.title or "",
            "description": resolved.description or "",
            "topics": list(resolved.topics),
            "platform": resolved.platform_name,
            "duration_seconds": round(probe_remote_duration(resolved), 3),
        })
    write_json(output / "selection.json", {
        "series_name": name, "profile_url": "", "selection_reason": selection_reason,
        "segmentation": SEGMENTATION_DURATION, "sources": sources,
    })
    progress("只读取第一来源开头一分钟，完整长视频留给 Action 下载")
    preview = output / "preview.mp4"
    probe = extract_remote_preview(sources[0], preview)
    manifest = output / "manifest.json"
    write_json(manifest, {"preview_only": True, "parts": [{
        "part_index": 1, "video_path": str(preview), "duration_seconds": probe["duration"],
        "title": sources[0].get("title") or "",
    }]})
    total_seconds = sum(float(item["duration_seconds"]) for item in sources)
    ranges = split_ranges(total_seconds)
    result = transcribe_intros(str(manifest), progress)
    return {**result, "preview_only": True, "selection_path": str(output / "selection.json"),
            "series_name": name, "source_count": len(sources),
            "split_plan": {"total_seconds": round(total_seconds, 3), "part_count": len(ranges),
                           "parts": [{"part_index": index, "start_seconds": round(start, 3),
                                      "end_seconds": round(end, 3),
                                      "duration_seconds": round(end - start, 3)}
                                     for index, (start, end) in enumerate(ranges, 1)]},
            "sources": [{key: item[key] for key in ("order", "title", "description", "topics",
                                                    "duration_seconds", "platform")} for item in sources],
            "next_step": "按拆分计划的段数准备封面，写含已完结的一套文案，再调用 anime_start_publication"}
