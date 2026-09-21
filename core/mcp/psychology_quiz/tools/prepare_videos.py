"""为心理测试分镜搜索、选择并规范化正版视频素材。"""

from __future__ import annotations

import hashlib
import json
from pathlib import Path

from core.tools.stock_video import download_stock_video, prepare_stock_clip, search_stock_videos

from .._constants import MCP_ID, STORYBOARD_CONTEXT_FILE_NAME, STORYBOARD_TEXT_FILE_NAME, VIDEO_SIZE
from .._errors import WorkflowStepError
from .draft import load_draft
from .narration import display_subtitle_text
from .storyboard import parse_storyboard


def prepare_video_searches(
    draft_path: str | Path,
    storyboard_text: str,
    *,
    video_config: dict,
    progress=None,
) -> dict:
    """逐镜头按三站兜底策略搜索候选视频，暂不下载。"""
    normalized_storyboard = str(storyboard_text or "").strip()
    if not normalized_storyboard:
        raise WorkflowStepError("storyboard_text 不能为空")
    if not isinstance(video_config, dict):
        raise WorkflowStepError("video_config 必须是对象")
    orientation = str(video_config.get("orientation") or "landscape").strip()
    per_provider = int(video_config.get("per_provider") or 8)
    providers = video_config.get("providers") or ["pexels", "pixabay", "coverr"]
    resolved_draft, draft = load_draft(draft_path, "心理测试稿件")
    cache_root = Path(str(draft.get("cache_dir") or "")).resolve()
    _, context = load_draft(cache_root / STORYBOARD_CONTEXT_FILE_NAME, "分镜上下文")
    timeline = context.get("timeline")
    if not isinstance(timeline, list) or not timeline:
        raise WorkflowStepError("分镜上下文缺少 timeline，请先完成 psychology_quiz_start_storyboard")
    shots = parse_storyboard(normalized_storyboard, timeline)
    storyboard_path = cache_root / STORYBOARD_TEXT_FILE_NAME
    storyboard_path.write_text(normalized_storyboard, encoding="utf-8")
    searches = []
    # 第一个镜头由写实静态图和片头动画承担，正文从第二个镜头开始使用实拍素材。
    stock_shots = shots[1:]
    if not stock_shots:
        raise WorkflowStepError("分镜至少需要两个镜头：片头动画后必须有正文视频素材")
    for index, shot in enumerate(stock_shots, 1):
        if progress:
            progress(f"正在搜索正版视频 {index}/{len(stock_shots)}")
        search = search_stock_videos(
            str(shot["prompt"]),
            orientation=orientation,
            per_provider=per_provider,
            providers=providers,
        )
        searches.append({
            "video_id": shot["id"],
            "subtitle": display_subtitle_text(str(shot.get("subtitle") or "")),
            "query": shot["prompt"],
            "duration": shot["duration"],
            "provider": search["provider"],
            "attempts": search["attempts"],
            "candidates": search["candidates"],
        })
    context_path = cache_root / "stock-videos" / "stock-video-context.json"
    context_path.parent.mkdir(parents=True, exist_ok=True)
    payload = {
        "version": 1,
        "status": "awaiting_stock_video_selection",
        "metadata": {
            "workflow": MCP_ID,
            "line": MCP_ID,
            "draft_path": str(resolved_draft),
            "storyboard_text": normalized_storyboard,
            "storyboard_path": str(storyboard_path),
            "storyboard_sha256": hashlib.sha256(normalized_storyboard.encode("utf-8")).hexdigest(),
            "video_config": {
                "orientation": orientation,
                "per_provider": per_provider,
                "providers": list(providers),
            },
            "tts_path": context.get("tts_path"),
        },
        "searches": searches,
        "selection_instructions": (
            "宿主 Agent 根据字幕、检索词、预览图、标题和时长选择每个镜头的视频。"
            "提交 [{video_id, provider, id}]；只能选择当前 context 返回的候选。"
        ),
        "intro_image_prompt": (
            "写实摄影风格，电影感自然光，16:9横屏，表现以下生活情境的关键瞬间："
            f"{draft['quiz']['scenario']}。人物表情真实、有悬念感，环境细节生活化，"
            "画面主体居中偏上，为底部字幕留出空间；禁止文字、字母、数字、水印、标志和拼贴。"
        ),
        "context_path": context_path.resolve().as_posix(),
    }
    context_path.write_text(json.dumps(payload, ensure_ascii=False, indent=2), encoding="utf-8")
    return payload


def download_selected_videos(context_path: str | Path, selections: list[dict], *, progress=None) -> dict:
    """下载选择结果、规范化镜头并写出视频素材清单。"""
    resolved_context, context = load_draft(context_path, "正版视频搜索上下文")
    searches = context.get("searches")
    metadata = context.get("metadata")
    if not isinstance(searches, list) or not isinstance(metadata, dict):
        raise WorkflowStepError("正版视频搜索上下文缺少 searches 或 metadata")
    if not isinstance(selections, list):
        raise WorkflowStepError("selections 必须是数组")
    by_video_id = {str(item["video_id"]): item for item in searches}
    selected_by_id = {str(item.get("video_id") or ""): item for item in selections}
    if set(selected_by_id) != set(by_video_id):
        raise WorkflowStepError(
            "视频选择没有完整覆盖全部镜头",
            {"expected": sorted(by_video_id), "actual": sorted(selected_by_id)},
        )
    output_root = resolved_context.parent
    raw_root = output_root / "raw"
    clip_root = output_root / "clips"
    frame_root = output_root / "frames"
    videos = {}
    frames = {}
    attributions = []
    for index, video_id in enumerate(by_video_id, 1):
        search = by_video_id[video_id]
        selection = selected_by_id[video_id]
        provider = str(selection.get("provider") or "")
        candidate_id = str(selection.get("id") or "")
        candidate = next(
            (
                row for row in search.get("candidates") or []
                if str(row.get("provider") or "") == provider and str(row.get("id") or "") == candidate_id
            ),
            None,
        )
        if not candidate:
            raise WorkflowStepError(f"镜头 {video_id} 选择了不在候选列表中的素材")
        if progress:
            progress(f"正在下载并处理正版视频 {index}/{len(by_video_id)}")
        downloaded = download_stock_video(candidate, raw_root / f"{video_id}-{provider}-{candidate_id}.mp4")
        prepared = prepare_stock_clip(
            downloaded["output_path"],
            clip_root / f"{video_id}.mp4",
            float(search["duration"]),
            size=VIDEO_SIZE,
            frame_path=frame_root / f"{video_id}.png",
        )
        videos[video_id] = prepared["output_path"]
        frames[video_id] = prepared["frame_path"]
        attributions.append({
            "video_id": video_id,
            "provider": provider,
            "source_id": candidate_id,
            "page_url": candidate["page_url"],
            "creator": candidate["creator"],
            "attribution": candidate["attribution"],
            "attribution_url": candidate["attribution_url"],
        })
    manifest_path = output_root / "stock-video-manifest.json"
    manifest = {
        "version": 1,
        "status": "ready",
        "videos": videos,
        "frames": frames,
        "attributions": attributions,
        "metadata": metadata,
        "manifest_path": str(manifest_path.resolve()),
    }
    manifest_path.write_text(json.dumps(manifest, ensure_ascii=False, indent=2), encoding="utf-8")
    return manifest
