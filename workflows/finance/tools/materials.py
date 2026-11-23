"""财经图片运镜、实拍素材搜索下载与混合镜头挂载。"""

from __future__ import annotations
import hashlib, json, threading, time, shutil, subprocess, random
from concurrent.futures import ThreadPoolExecutor, as_completed
from pathlib import Path
from tools.generate_stock_video import (
    download_stock_video,
    prepare_stock_clip,
    search_stock_videos,
    select_stock_candidates,
    StockVideoError,
)
from tools.generate_stock_video._constants import SELECTION_DURATION_MARGIN_SECONDS
from workflows.finance.parameters import (
    MATERIAL_STOCK_VIDEO,
    IMAGE_MOTION_EFFECTS,
    MCP_ID,
    STORYBOARD_CONTEXT_FILE_NAME,
    STORYBOARD_TEXT_FILE_NAME,
    VIDEO_SIZE,
    VIDEO_RADIO,
    ENDING_VIDEO_PATH,
)
from workflows.finance.errors.exceptions import WorkflowStepError
from workflows.finance.tools.storyboard import display_subtitle_text, parse_storyboard
from workflows.finance.tools.drafts import load_draft
from tools.generate_final_video._ffmpeg import _probe
from tools.generate_shot import generate_shot_from_image
from workflows.finance.tools.storyboard_images import save_storyboard_images, bind_storyboard_images


DEFAULT_SOFT_BLUR_SIGMA = 0.55


def prepare_image_materials(draft_path: str | Path, image_paths: list[str]) -> dict:
    """接收宿主按镜头顺序生成的图片，保存为工作流素材清单。"""
    resolved_draft, draft = load_draft(draft_path, "财经稿件")
    cache_root = Path(draft["cache_dir"])
    _, context = load_draft(cache_root / STORYBOARD_CONTEXT_FILE_NAME, "配音上下文")
    shots = parse_storyboard(draft["storyboard"], context["timeline"])[:-1]
    if len(image_paths) != len(shots):
        raise WorkflowStepError(f"需要 {len(shots)} 张分镜图片，收到 {len(image_paths)} 张")
    images = {}
    for shot, supplied_path in zip(shots, image_paths):
        path = Path(supplied_path).resolve()
        if not path.is_file():
            raise WorkflowStepError(f"镜头 {shot['id']} 的图片不存在：{path}")
        images[shot["id"]] = str(path)
    save_storyboard_images(draft["source_aweme_id"], draft["storyboard"], images)
    bind_storyboard_images(draft)
    manifest_path = cache_root / "generated-images" / "image-material-manifest.json"
    manifest_path.parent.mkdir(parents=True, exist_ok=True)
    manifest = {"images": images, "image_motion": {key: dict(random.choice(IMAGE_MOTION_EFFECTS)) for key in images},
                "normalized_cfr": True,
                "metadata": {"draft_path": str(resolved_draft), "material_strategy": "generated_images",
                             "storyboard_text": draft["storyboard"],
                             "storyboard_sha256": _storyboard_hash(draft["storyboard"])},
                "manifest_path": str(manifest_path)}
    manifest_path.write_text(json.dumps(manifest, ensure_ascii=False, indent=2), encoding="utf-8")
    return manifest


def prepare_video_searches(
    draft_path: str | Path,
    storyboard_text: str,
    *,
    video_config: dict,
    progress=None,
) -> dict:
    """优先使用已有图片，仅为其余镜头搜索 Pexels 视频。"""
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
    resolved_draft, draft = load_draft(draft_path, "财经稿件")
    cache_root = Path(str(draft.get("cache_dir") or "")).resolve()
    _, context = load_draft(cache_root / STORYBOARD_CONTEXT_FILE_NAME, "分镜上下文")
    timeline = context.get("timeline")
    if not isinstance(timeline, list) or not timeline:
        raise WorkflowStepError("分镜上下文缺少 timeline，请先完成 finance_start_production")
    shots = parse_storyboard(normalized_storyboard, timeline)[:-1]
    storyboard_path = cache_root / STORYBOARD_TEXT_FILE_NAME
    storyboard_path.write_text(normalized_storyboard, encoding="utf-8")
    searches = []
    # 片头也独立选片，避免借用下一镜头后再次从头播放。
    images = {}
    for shot in shots:
        for suffix in (".png", ".jpg", ".jpeg", ".webp"):
            path = cache_root / "generated-images" / f"{shot['id']}{suffix}"
            if path.is_file():
                images[shot["id"]] = str(path)
                break
    if images:
        save_storyboard_images(draft["source_aweme_id"], draft["storyboard"], images)
        bind_storyboard_images(draft)
    stock_shots = [shot for shot in shots if shot["id"] not in images]
    for shot_id in images:
        print(f"[素材选择 {shot_id}] 发现图片，跳过视频检索", flush=True)
    def search_shot(shot):
        label = f"[素材检索 {shot['id']}]"
        try:
            search = search_stock_videos(
                str(shot["keywords"]),
                orientation=orientation,
                aspect_ratio=VIDEO_RADIO,
                per_provider=per_provider,
                min_duration=float(shot["duration"]),
                max_clips=2,
            )
        except StockVideoError as exc:
            required = float(shot["duration"]) + SELECTION_DURATION_MARGIN_SECONDS
            lines = [f"{label} 失败：{exc}",
                     f"台词：{','.join(shot['line_ids'])}",
                     f"画面：{shot['description']}",
                     f"关键词：{shot['keywords']}",
                     f"镜头 {shot['duration']:.3f} 秒；素材需 ≥{required:.3f} 秒，最多拼 2 段；比例 {VIDEO_RADIO}，不限制分辨率"]
            for attempt in exc.details.get("attempts", []):
                lines.append(f"Pexels 返回 {attempt['count']} 条，缓存命中：{attempt['cache_hit']}")
            for candidate in exc.details.get("candidates", []):
                reasons = candidate["excluded_reasons"]
                status = "；".join(reasons) if reasons else (
                    "比例合格，单段时长足够" if candidate["duration"] >= required
                    else "比例合格，单段时长不足，可参与拼接")
                lines.append(f"候选 {candidate['id']}：{candidate['width']}×{candidate['height']}，"
                             f"{candidate['duration']:.3f} 秒；{status}")
            if exc.details.get("candidates"):
                durations = sorted((row["duration"] for row in exc.details["candidates"]
                                    if not row["excluded_reasons"]), reverse=True)
                lines.append(f"比例合格 {len(durations)} 条；最长两段合计 {sum(durations[:2]):.3f} 秒，"
                             f"要求 ≥{required:.3f} 秒。")
                lines.append("结论：上述候选中不存在满足要求的单段或两段组合。")
            print("\n".join(lines), flush=True)
            raise
        print(f"{label} 成功：关键词={shot['keywords']}；镜头={shot['duration']:.3f} 秒；"
              f"达标候选={len(search['candidates'])} 条", flush=True)
        return {
            "video_id": shot["id"],
            "subtitle": display_subtitle_text(str(shot.get("subtitle") or "")),
            "description": shot["description"],
            "query": shot["keywords"],
            "duration": shot["duration"],
            "provider": search["provider"],
            "attempts": search["attempts"],
            "candidates": search["candidates"],
        }
    # 网络搜索有限并发；按分镜原顺序保存，完成顺序不影响选片与成片顺序。
    with ThreadPoolExecutor(max_workers=max(1, min(3, len(stock_shots)))) as executor:
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
            "material_strategy": "mixed_media" if images and stock_shots else "generated_images" if images else MATERIAL_STOCK_VIDEO,
            "draft_path": str(resolved_draft),
            "storyboard_text": normalized_storyboard,
            "storyboard_path": str(storyboard_path),
            "storyboard_sha256": hashlib.sha256(normalized_storyboard.encode("utf-8")).hexdigest(),
            "video_config": {
                "orientation": orientation,
                "per_provider": per_provider,
                "soft_blur_sigma": video_config.get("soft_blur_sigma"),
            },
            "tts_path": context.get("tts_path"),
        },
        "searches": searches,
        "images": images,
        "image_motion": {key: dict(random.choice(IMAGE_MOTION_EFFECTS)) for key in images},
        "selection_instructions": (
            f"按搜索顺序取 {VIDEO_RADIO} 素材，不限制分辨率。网站标注时长须比镜头实际需要多 "
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
    if not isinstance(searches, list) or not isinstance(metadata, dict):
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
    planned = {}
    used_sources: set[tuple[str, str]] = set()
    for video_id, search in by_video_id.items():
        candidates = search.get("candidates") or []
        if video_id in selected_by_id:
            selection = selected_by_id[video_id]
            candidates = [row for row in candidates if str(row.get("provider")) == str(selection.get("provider"))
                          and str(row.get("id")) == str(selection.get("id"))]
        candidates = [row for row in candidates if (str(row.get("provider")), str(row.get("id"))) not in used_sources]
        chosen = select_stock_candidates(candidates, float(search["duration"]), 0, 0)
        if not chosen:
            raise WorkflowStepError(
                f"镜头 {video_id} 没有单段或两段合计比实际需要多 {SELECTION_DURATION_MARGIN_SECONDS:g} 秒、且未被其他镜头使用的视频"
            )
        planned[video_id] = chosen
        print(f"[素材选片 {video_id}] 采用 "
              + " + ".join(f"{row['id']}（{row['width']}×{row['height']}，{float(row['duration']):.3f} 秒）"
                           for row in chosen)
              + f"；目标镜头 {float(search['duration']):.3f} 秒", flush=True)
        used_sources.update((str(row["provider"]), str(row["id"])) for row in chosen)

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
    with ThreadPoolExecutor(max_workers=max(1, min(3, len(planned)))) as executor:
        futures = {executor.submit(process, video_id): video_id for video_id in planned}
        for future in as_completed(futures):
            video_id = futures[future]
            results[video_id] = future.result()
            if progress:
                action = "复用已完成镜头" if results[video_id]["prepared"]["cache_hit"] else "下载与处理完成"
                progress(f"{action} {len(results)}/{len(planned)}：{video_id}")
    manifest_path = output_root / "stock-video-manifest.json"
    manifest = {
        "version": 2, "status": "ready", "material_strategy": metadata["material_strategy"],
        "soft_blur_sigma": sigma, "normalized_cfr": True,
        "images": context["images"], "image_motion": context["image_motion"],
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


def _ensure_clip_durations(
    shots: list[dict],
    cache_root: Path,
    source_groups: dict,
    progress=None,
    soft_blur_sigma: float = 0,
) -> None:
    """片段时长与当前分镜不符时，从原始素材重裁。

    配音换音色/改语速后时间轴会变，而 clips 是按旧时长裁好的缓存；
    不重裁会让成片总长与配音不匹配（画面、字幕对不上，末尾配音被截）。
    """
    for shot in shots:
        clip = Path(shot["segment_path"])
        available = float(_probe(clip)["duration"])
        target = float(shot["duration"])
        if abs(available - target) <= 0.05:
            continue
        if progress:
            progress(f"重裁镜头 {shot['id']}：{available:.2f}s -> {target:.2f}s")
        prepare_stock_clip(
            source_groups[shot["id"]],
            clip,
            target,
            size=VIDEO_SIZE,
            frame_path=cache_root / "stock-videos" / "frames" / f"{shot['id']}.png",
            soft_blur_sigma=soft_blur_sigma,
        )


def _storyboard_hash(value: str) -> str:
    return hashlib.sha256(value.encode("utf-8")).hexdigest()


def _load_saved_storyboard(material_metadata: dict) -> str:
    saved = material_metadata["storyboard_text"]
    expected_hash = material_metadata["storyboard_sha256"]
    if _storyboard_hash(saved) != expected_hash:
        raise WorkflowStepError("已保存的分镜文本损坏，请重新准备镜头素材")
    return saved


def _render_ending_video(shot: dict, cache_root: Path) -> None:
    """复用已含配音和字幕的预制片尾画面，音轨由完整旁白统一混合。"""
    from workflows.finance.tools.prepared_outro import outro_resources
    resources = outro_resources()
    shot["segment_path"] = str(resources["video"])



def _apply_material(
    manifest: dict,
    shots: list[dict],
    *,
    resolved_draft: Path,
    cache_root: Path,
    progress,
) -> tuple[bool, list[str]]:
    """按素材清单类型挂载镜头，返回 (是否实拍视频策略, 封面源图)。"""
    material_metadata = manifest["metadata"]
    if Path(str(material_metadata.get("draft_path") or "")).resolve() != resolved_draft:
        raise WorkflowStepError("素材清单不属于当前稿件，请重新准备镜头素材")
    _render_ending_video(shots[-1], cache_root)
    shots = shots[:-1]
    images = manifest.get("images", {})
    for shot in shots:
        if shot["id"] not in images:
            continue
        shot["image_path"] = images[shot["id"]]
        shot["frame_path"] = shot["image_path"]
        shot["motion"] = manifest["image_motion"][shot["id"]]
        print(f"[图片动效 {shot['id']}] {shot['motion']['name']}，时长 {shot['duration']:.3f} 秒", flush=True)
        if shot is shots[0]:
            continue
        rendered = generate_shot_from_image(
            shot["image_path"], cache_root / "image-clips" / f"{shot['id']}.mp4",
            size=VIDEO_SIZE, duration=shot["duration"], motion=shot["motion"],
        )
        shot["segment_path"] = rendered["output_path"]
    videos = manifest.get("videos")
    if isinstance(videos, dict) and videos:
        frames = manifest.get("frames")
        expected_ids = {shot["id"] for shot in shots} - set(images)
        if set(videos) != expected_ids:
            raise WorkflowStepError(
                "视频素材清单必须为片头和正文各自提供独立素材，请重新搜索并下载素材",
                {"expected_video_ids": sorted(expected_ids), "actual_video_ids": sorted(videos)},
            )
        if not isinstance(frames, dict) or set(frames) != expected_ids:
            raise WorkflowStepError("视频素材清单缺少完整封面帧")
        for video_id, video_path in videos.items():
            if not Path(str(video_path)).resolve().is_file():
                raise WorkflowStepError(f"视频素材不存在：{video_id} -> {video_path}")
        video_shots = [shot for shot in shots if shot["id"] not in images]
        for shot in video_shots:
            shot["segment_path"] = str(Path(videos[shot["id"]]).resolve())
            shot["frame_path"] = str(Path(frames[shot["id"]]).resolve())
        raw_sources = manifest["raw_sources"]
        _ensure_clip_durations(video_shots, cache_root, raw_sources, progress,
                               float(manifest["soft_blur_sigma"]))
        if shots[0]["id"] not in images:
            first_video = raw_sources[shots[0]["id"]][0]
            ffmpeg = shutil.which("ffmpeg")
            if not ffmpeg:
                raise WorkflowStepError("找不到 ffmpeg，无法提取片头首帧")
            resolved_intro_image = cache_root / "stock-videos" / "intro-first-frame.png"
            extracted = subprocess.run(
                [ffmpeg, "-hide_banner", "-loglevel", "error", "-y", "-i", str(first_video),
                 "-frames:v", "1", str(resolved_intro_image)],
                capture_output=True, text=True, encoding="utf-8", errors="replace", timeout=120,
            )
            if extracted.returncode or not resolved_intro_image.is_file():
                raise WorkflowStepError(f"提取原视频首帧失败：{extracted.stderr[-1500:]}")
            shots[0]["intro_video_path"] = shots[0]["segment_path"]
            shots[0]["image_path"] = str(resolved_intro_image)
            shots[0]["frame_path"] = str(resolved_intro_image)
        # 封面可使用正文视频帧或替代对应镜头的图片。
        return True, [str(shot["frame_path"]) for shot in shots[1:]]
    if images:
        return False, [str(shot["frame_path"]) for shot in shots]
    raise WorkflowStepError("素材清单缺少图片或视频")


def _write_attributions(
    manifest: dict,
    settings: dict,
    output_root: Path,
) -> str | None:
    attributions = list(manifest.get("attributions") or [])
    if not attributions:
        return None
    seen_sources: set[tuple[str, str]] = set()
    attribution_lines: list[str] = []
    for item in attributions:
        if not isinstance(item, dict):
            continue
        source_key = (str(item.get("provider") or ""), str(item.get("source_id") or ""))
        if source_key in seen_sources:
            continue
        seen_sources.add(source_key)
        label = str(item.get("attribution") or item.get("provider") or "素材来源").strip()
        url = str(item.get("attribution_url") or item.get("page_url") or "").strip()
        attribution_lines.append(f"{label} {url}".strip())
    if settings.get("bgm_credit"):
        attribution_lines.append(str(settings["bgm_credit"]))
    path = output_root / "attribution-comment.txt"
    path.write_text("\n".join(attribution_lines) + "\n", encoding="utf-8")
    return str(path)
