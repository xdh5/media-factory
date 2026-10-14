"""正版实拍视频素材策略：逐镜头搜索、选择、下载并规范化为与配音一致的镜头。

这是财经线的默认素材策略，与参考图千问生图并列。
第一个镜头使用第一段原始实拍视频首帧制作片头动画，正文从第二个镜头开始使用实拍素材。
"""

from __future__ import annotations

import hashlib
import json
import threading
import time
from concurrent.futures import ThreadPoolExecutor, as_completed
from pathlib import Path

from core.tools.stock_video import download_stock_video, prepare_stock_clip, search_stock_videos, select_stock_candidates
from core.tools.stock_video._constants import SELECTION_DURATION_MARGIN_SECONDS

from ..config.settings import (
    MATERIAL_STOCK_VIDEO,
    MCP_ID,
    STORYBOARD_CONTEXT_FILE_NAME,
    STORYBOARD_TEXT_FILE_NAME,
    VIDEO_SIZE,
)
from ..errors import WorkflowStepError
from .narration import display_subtitle_text
from .save_draft import load_draft
from .storyboard import parse_storyboard

DEFAULT_SOFT_BLUR_SIGMA = 0.55


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
    try:
        per_provider = int(video_config.get("per_provider") or 8)
    except (TypeError, ValueError) as exc:
        raise WorkflowStepError("video_config.per_provider 必须是整数") from exc
    providers = video_config.get("providers") or ["pexels", "pixabay", "coverr"]
    resolved_draft, draft = load_draft(draft_path, "财经稿件")
    cache_root = Path(str(draft.get("cache_dir") or "")).resolve()
    _, context = load_draft(cache_root / STORYBOARD_CONTEXT_FILE_NAME, "分镜上下文")
    timeline = context.get("timeline")
    if not isinstance(timeline, list) or not timeline:
        raise WorkflowStepError("分镜上下文缺少 timeline，请先完成 finance_start_storyboard")
    shots = parse_storyboard(normalized_storyboard, timeline)
    storyboard_path = cache_root / STORYBOARD_TEXT_FILE_NAME
    storyboard_path.write_text(normalized_storyboard, encoding="utf-8")
    searches = []
    # 第一个镜头由写实静态图和片头动画承担，正文从第二个镜头开始使用实拍素材。
    stock_shots = shots[1:]
    if not stock_shots:
        raise WorkflowStepError("分镜至少需要两个镜头：片头动画后必须有正文视频素材")
    def search_shot(shot):
        search = search_stock_videos(
            str(shot["prompt"]),
            orientation=orientation,
            per_provider=per_provider,
            providers=providers,
            min_duration=float(shot["duration"]),
            min_width=int(VIDEO_SIZE.split("x")[0]),
            min_height=int(VIDEO_SIZE.split("x")[1]),
            max_clips=2,
        )
        return {
            "video_id": shot["id"],
            "subtitle": display_subtitle_text(str(shot.get("subtitle") or "")),
            "query": shot["prompt"],
            "duration": shot["duration"],
            "provider": search["provider"],
            "attempts": search["attempts"],
            "candidates": search["candidates"],
        }
    # 网络搜索有限并发；按分镜原顺序保存，完成顺序不影响选片与成片顺序。
    with ThreadPoolExecutor(max_workers=min(3, len(stock_shots))) as executor:
        futures = [executor.submit(search_shot, shot) for shot in stock_shots]
        completed = {}
        for future in as_completed(futures):
            result = future.result()
            completed[result["video_id"]] = result
            if progress:
                progress(f"正在搜索正版视频 {len(completed)}/{len(stock_shots)}")
    searches = [completed[shot["id"]] for shot in stock_shots]
    context_path = cache_root / "stock-videos" / "stock-video-context.json"
    context_path.parent.mkdir(parents=True, exist_ok=True)
    payload = {
        "version": 1,
        "status": "ready_to_download",
        "metadata": {
            "workflow": MCP_ID,
            "line": MCP_ID,
            "material_strategy": MATERIAL_STOCK_VIDEO,
            "draft_path": str(resolved_draft),
            "storyboard_text": normalized_storyboard,
            "storyboard_path": str(storyboard_path),
            "storyboard_sha256": hashlib.sha256(normalized_storyboard.encode("utf-8")).hexdigest(),
            "video_config": {
                "orientation": orientation,
                "per_provider": per_provider,
                "providers": list(providers),
                "soft_blur_sigma": video_config.get("soft_blur_sigma"),
            },
            "tts_path": context.get("tts_path"),
        },
        "searches": searches,
        "selection_instructions": (
            "按搜索顺序取尺寸达标的素材。网站标注时长须比镜头实际需要多 "
            f"{SELECTION_DURATION_MARGIN_SECONDS:g} 秒，单段不足时拼两段，合计也要多出这 {SELECTION_DURATION_MARGIN_SECONDS:g} 秒；"
            "调用下载工具时无需传 selections。"
        ),
        "context_path": context_path.resolve().as_posix(),
    }
    context_path.write_text(json.dumps(payload, ensure_ascii=False, indent=2), encoding="utf-8")
    return payload


def download_selected_videos(context_path: str | Path, selections: list[dict] | None = None, *, progress=None) -> dict:
    """并发下载并一次完成拼接、规范化与磨砂；重试复用已完成镜头。"""
    started = time.monotonic()
    resolved_context, context = load_draft(context_path, "正版视频搜索上下文")
    searches, metadata = context.get("searches"), context.get("metadata")
    if not isinstance(searches, list) or not searches or not isinstance(metadata, dict):
        raise WorkflowStepError("正版视频搜索上下文缺少 searches 或 metadata")
    video_config = metadata.get("video_config") or {}
    try:
        raw_sigma = video_config.get("soft_blur_sigma")
        sigma = DEFAULT_SOFT_BLUR_SIGMA if raw_sigma is None else float(raw_sigma)
    except (TypeError, ValueError) as exc:
        raise WorkflowStepError("soft_blur_sigma 必须是数字") from exc
    by_video_id = {str(item["video_id"]): item for item in searches}
    if selections is not None:
        if not isinstance(selections, list) or any(not isinstance(item, dict) for item in selections):
            raise WorkflowStepError("selections 必须是对象数组")
        if len(selections) != len(by_video_id) or {str(item.get("video_id") or "") for item in selections} != set(by_video_id):
            raise WorkflowStepError("视频选择没有完整覆盖全部镜头")
    selected_by_id = {str(item["video_id"]): item for item in selections or []}
    width, height = map(int, VIDEO_SIZE.split("x"))
    planned = {}
    for video_id, search in by_video_id.items():
        candidates = search.get("candidates") or []
        if video_id in selected_by_id:
            selection = selected_by_id[video_id]
            candidates = [row for row in candidates if str(row.get("provider")) == str(selection.get("provider"))
                          and str(row.get("id")) == str(selection.get("id"))]
        chosen = select_stock_candidates(candidates, float(search["duration"]), width, height)
        if not chosen:
            raise WorkflowStepError(
                f"镜头 {video_id} 没有单段或两段合计比实际需要多 {SELECTION_DURATION_MARGIN_SECONDS:g} 秒、且尺寸达标的视频，请重新搜索"
            )
        planned[video_id] = chosen

    output_root = resolved_context.parent
    raw_root, clip_root, frame_root = (output_root / name for name in ("raw", "clips", "frames"))
    locks = {(row["provider"], row["id"]): threading.Lock() for chosen in planned.values() for row in chosen}

    def process(video_id):
        shot_started = time.monotonic()
        chosen = planned[video_id]
        sources, credits = [], []
        download_seconds = 0.0
        downloaded_count = 0
        for row in chosen:
            provider, source_id = row["provider"], row["id"]
            download_started = time.monotonic()
            # 同一期不同镜头使用同一素材时只下载一次，锁保护原子下载临时文件。
            with locks[(provider, source_id)]:
                existing = raw_root / f"{video_id}-{provider}-{source_id}.mp4"
                destination = existing if existing.is_file() else raw_root / f"{provider}-{source_id}.mp4"
                downloaded = download_stock_video(row, destination)
            download_seconds += time.monotonic() - download_started
            downloaded_count += int(not downloaded.get("skipped_existing"))
            sources.append(downloaded["output_path"])
            credits.append({"video_id": video_id, "provider": provider, "source_id": source_id,
                            **{key: row[key] for key in ("page_url", "creator", "attribution", "attribution_url")}})
        prepared = prepare_stock_clip(sources, clip_root / f"{video_id}.mp4", float(by_video_id[video_id]["duration"]),
                                      size=VIDEO_SIZE, frame_path=frame_root / f"{video_id}.png", soft_blur_sigma=sigma)
        return {"prepared": prepared, "sources": sources, "credits": credits,
                "timing": {"total_seconds": round(time.monotonic() - shot_started, 3),
                           "download_seconds": round(download_seconds, 3),
                           "downloaded_count": downloaded_count, "cache_hit": prepared["cache_hit"]}}

    results = {}
    # 限制并发与每个编码进程的线程数，避免所有镜头抢满 CPU 和内存。
    with ThreadPoolExecutor(max_workers=min(3, len(planned))) as executor:
        futures = {executor.submit(process, video_id): video_id for video_id in planned}
        for future in as_completed(futures):
            video_id = futures[future]
            results[video_id] = future.result()
            if progress:
                action = "复用已完成镜头" if results[video_id]["prepared"]["cache_hit"] else "下载与处理完成"
                progress(f"{action} {len(results)}/{len(planned)}：{video_id}")
    manifest_path = output_root / "stock-video-manifest.json"
    manifest = {
        "version": 2, "status": "ready", "material_strategy": MATERIAL_STOCK_VIDEO,
        "soft_blur_sigma": sigma, "normalized_cfr": True,
        "videos": {key: results[key]["prepared"]["output_path"] for key in planned},
        "frames": {key: results[key]["prepared"]["frame_path"] for key in planned},
        "raw_sources": {key: results[key]["sources"] for key in planned},
        "attributions": [credit for key in planned for credit in results[key]["credits"]],
        "timings": {key: results[key]["timing"] for key in planned},
        "elapsed_seconds": round(time.monotonic() - started, 3),
        "metadata": metadata, "manifest_path": str(manifest_path.resolve()),
    }
    temporary_manifest = manifest_path.with_suffix(".json.tmp")
    temporary_manifest.write_text(json.dumps(manifest, ensure_ascii=False, indent=2), encoding="utf-8")
    temporary_manifest.replace(manifest_path)
    return manifest

def build_stock_video_selection_prompt(context_path: str | Path, feedback: str = "") -> dict:
    """基于搜索上下文返回宿主 Agent 与 Runner 共用的选视频 Prompt。"""
    _, context = load_draft(context_path, "正版视频搜索上下文")
    searches = context.get("searches")
    if not isinstance(searches, list) or not searches:
        raise WorkflowStepError("正版视频搜索上下文缺少 searches")
    compact = []
    for search in searches:
        compact.append({
            "video_id": search["video_id"],
            "subtitle": search.get("subtitle"),
            "query": search.get("query"),
            "duration": search.get("duration"),
            "candidates": [
                {
                    "provider": row.get("provider"),
                    "id": row.get("id"),
                    "title": row.get("title"),
                    "duration": row.get("duration"),
                    "width": row.get("width"),
                    "height": row.get("height"),
                    "preview_url": row.get("preview_url"),
                }
                for row in search.get("candidates") or []
            ],
        })
    prompt = (
        "为每个正文镜头选择语义最贴近、横屏构图最合适的正版实拍候选视频。"
        f"网站标注时长必须比镜头实际需要至少多 {SELECTION_DURATION_MARGIN_SECONDS:g} 秒；单段不够时，两段合计也要多出这 {SELECTION_DURATION_MARGIN_SECONDS:g} 秒。"
        "必须检查可用预览画面；同一期尽量不重复素材；只能选择输入候选。\n"
        f"搜索结果：{json.dumps(compact, ensure_ascii=False)}\n"
        "只输出 JSON：{\"selections\":[{\"video_id\":\"shot-002\","
        "\"provider\":\"pexels\",\"id\":\"123\"}]}，完整覆盖全部正文镜头。"
    )
    if feedback:
        prompt += f"\n\n上一次校验失败：{feedback}"
    return {"system_prompt": "你是财经视频正版实拍素材选择员，必须输出有效 JSON，不要输出 Markdown。", "user_prompt": prompt}


def validate_stock_video_selection_response(context_path: str | Path, response_text: str) -> dict:
    """解析模型选片结果并复用下载阶段的候选覆盖校验。"""
    _, context = load_draft(context_path, "正版视频搜索上下文")
    try:
        payload = json.loads(str(response_text or "").strip().removeprefix("```json").removesuffix("```").strip())
    except json.JSONDecodeError as exc:
        raise WorkflowStepError(f"选视频结果不是有效 JSON：{exc}") from exc
    selections = payload.get("selections") if isinstance(payload, dict) else None
    if not isinstance(selections, list):
        raise WorkflowStepError("选视频结果缺少 selections 数组")
    expected = {str(item.get("video_id") or "") for item in context.get("searches") or []}
    normalized = [
        {
            "video_id": str(item.get("video_id") or ""),
            "provider": str(item.get("provider") or ""),
            "id": str(item.get("id") or ""),
        }
        for item in selections
        if isinstance(item, dict)
    ]
    if len(normalized) != len(expected) or {item["video_id"] for item in normalized} != expected:
        raise WorkflowStepError("视频选择没有逐项完整覆盖全部正文镜头")
    by_video_id = {str(item["video_id"]): item for item in context.get("searches") or []}
    for item in normalized:
        candidates = by_video_id[item["video_id"]].get("candidates") or []
        if not any(str(row.get("provider") or "") == item["provider"] and str(row.get("id") or "") == item["id"] for row in candidates):
            raise WorkflowStepError(f"镜头 {item['video_id']} 选择了不在候选列表中的素材")
    return {"selections": normalized}
