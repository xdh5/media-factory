"""财经视频素材与分镜清单处理。"""

from __future__ import annotations

import hashlib
import shutil
import subprocess
from pathlib import Path
from core.tools.generate_final_video._ffmpeg import _probe
from core.tools.stock_video import prepare_stock_clip
from ..config.settings import STORYBOARD_TEXT_FILE_NAME, VIDEO_SIZE
from ..errors import WorkflowStepError


def _raw_source_hints(manifest: dict, cache_root: Path) -> dict[str, Path]:
    """按素材清单的署名记录定位每个镜头当初选中的原始素材。

    raw 目录里同时留着同一镜头的多个候选（搜索阶段下载的备选），
    只按文件名排序取第一个会在重裁时把镜头换成没被选中的候选，
    所以优先用 attribution 里的 provider + source_id 还原真实素材。
    """
    hints: dict[str, Path] = {}
    for shot_id, sources in (manifest.get("raw_sources") or {}).items():
        if sources and Path(sources[0]).is_file():
            hints[shot_id] = Path(sources[0])
    for item in manifest.get("attributions") or []:
        if not isinstance(item, dict):
            continue
        shot_id = str(item.get("video_id") or "").strip()
        provider = str(item.get("provider") or "").strip()
        source_id = str(item.get("source_id") or "").strip()
        if not (shot_id and provider and source_id):
            continue
        candidate = cache_root / "stock-videos" / "raw" / f"{shot_id}-{provider}-{source_id}.mp4"
        if candidate.is_file() and shot_id not in hints:
            hints[shot_id] = candidate
    return hints


def _ensure_clip_durations(
    shots: list[dict],
    cache_root: Path,
    progress=None,
    raw_hints: dict[str, Path] | None = None,
    source_groups: dict | None = None,
    soft_blur_sigma: float = 0,
) -> None:
    """片段时长与当前分镜不符时，从原始素材重裁。

    配音换音色/改语速后时间轴会变，而 clips 是按旧时长裁好的缓存；
    不重裁会让成片总长与配音不匹配（画面、字幕对不上，末尾配音被截）。
    """
    hints = raw_hints or {}
    for shot in shots:
        clip = Path(str(shot.get("segment_path") or ""))
        if not clip.is_file():
            continue
        try:
            available = float(_probe(clip)["duration"])
        except Exception:
            continue
        target = float(shot.get("duration") or 0)
        if target <= 0 or abs(available - target) <= 0.05:
            continue
        hinted = hints.get(shot["id"])
        raw_candidates = [hinted] if hinted else sorted(
            (cache_root / "stock-videos" / "raw").glob(f"{shot['id']}-*.mp4")
        )
        if not raw_candidates:
            raise WorkflowStepError(
                f"镜头 {shot['id']} 时长已变（{available:.2f}s -> {target:.2f}s），但找不到原始素材无法重裁"
            )
        if progress:
            progress(f"重裁镜头 {shot['id']}：{available:.2f}s -> {target:.2f}s")
        prepare_stock_clip(
            (source_groups or {}).get(shot["id"]) or raw_candidates[0],
            clip,
            target,
            size=VIDEO_SIZE,
            frame_path=cache_root / "stock-videos" / "frames" / f"{shot['id']}.png",
            soft_blur_sigma=soft_blur_sigma,
        )


def _storyboard_hash(value: str) -> str:
    return hashlib.sha256(value.encode("utf-8")).hexdigest()


def _load_saved_storyboard(
    material_metadata: dict,
    cache_root: Path,
    storyboard_text: str | None,
) -> str:
    saved = str(material_metadata.get("storyboard_text") or "").strip()
    saved_path = Path(str(material_metadata.get("storyboard_path") or "")).resolve()
    if not saved and saved_path.is_file():
        saved = saved_path.read_text(encoding="utf-8").strip()
    fallback_path = cache_root / STORYBOARD_TEXT_FILE_NAME
    if not saved and fallback_path.is_file():
        saved = fallback_path.read_text(encoding="utf-8").strip()
    if saved:
        expected_hash = str(material_metadata.get("storyboard_sha256") or "").strip()
        if expected_hash and _storyboard_hash(saved) != expected_hash:
            raise WorkflowStepError(
                "已保存的分镜文本损坏，请重新准备镜头素材",
                {"storyboard_sha256": expected_hash},
            )
        return saved
    fallback = str(storyboard_text or "").strip()
    if not fallback:
        raise WorkflowStepError(
            "素材清单里没有分镜文本。请重新调用 finance_prepare_images / finance_start_video_search，出片不必再传 storyboard_text"
        )
    expected_hash = str(material_metadata.get("storyboard_sha256") or "").strip()
    if expected_hash and _storyboard_hash(fallback) != expected_hash:
        raise WorkflowStepError(
            "传入的 storyboard_text 与准备素材时不一致。请重新准备素材后直接 finance_finish_video",
            {"storyboard_sha256": expected_hash, "received_sha256": _storyboard_hash(fallback)},
        )
    return fallback


def _apply_material(
    manifest: dict,
    shots: list[dict],
    *,
    resolved_draft: Path,
    intro_image_path: str | Path | None,
    cache_root: Path,
    progress,
) -> tuple[bool, list[str]]:
    """按素材清单类型挂载镜头，返回 (是否实拍视频策略, 封面源图)。"""
    material_metadata = manifest.get("metadata")
    if not isinstance(material_metadata, dict):
        raise WorkflowStepError("素材清单缺少 metadata")
    if Path(str(material_metadata.get("draft_path") or "")).resolve() != resolved_draft:
        raise WorkflowStepError("素材清单不属于当前稿件，请重新准备镜头素材")
    videos = manifest.get("videos")
    if isinstance(videos, dict) and videos:
        frames = manifest.get("frames")
        if len(shots) < 2:
            raise WorkflowStepError("分镜至少需要两个镜头：片头动画后必须有正文视频素材")
        expected_ids = {shot["id"] for shot in shots[1:]}
        if set(videos) != expected_ids:
            raise WorkflowStepError(
                "视频素材清单没有完整覆盖所有镜头",
                {"expected_video_ids": sorted(expected_ids), "actual_video_ids": sorted(videos)},
            )
        if not isinstance(frames, dict) or set(frames) != expected_ids:
            raise WorkflowStepError("视频素材清单缺少完整封面帧")
        for video_id, video_path in videos.items():
            if not Path(str(video_path)).resolve().is_file():
                raise WorkflowStepError(f"视频素材不存在：{video_id} -> {video_path}")
        for shot in shots[1:]:
            shot["segment_path"] = str(Path(videos[shot["id"]]).resolve())
            shot["frame_path"] = str(Path(frames[shot["id"]]).resolve())
        _ensure_clip_durations(shots[1:], cache_root, progress, _raw_source_hints(manifest, cache_root),
                               manifest.get("raw_sources"), float(manifest.get("soft_blur_sigma") or 0))
        first_video_id = shots[1]["id"]
        raw_sources = _raw_source_hints(manifest, cache_root)
        first_video = raw_sources.get(first_video_id)
        if first_video is None:
            raise WorkflowStepError("第一段正文视频缺少原始下载素材，无法提取清晰片头首帧")
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
        shots[0]["image_path"] = str(resolved_intro_image)
        shots[0]["frame_path"] = str(resolved_intro_image)
        # 封面底图来自正文实拍视频帧，片头单独使用第一段原视频首帧。
        return True, [str(shot["frame_path"]) for shot in shots[1:]]
    images = manifest.get("images")
    expected_image_ids = {shot["id"] for shot in shots}
    if not isinstance(images, dict) or set(images) != expected_image_ids:
        raise WorkflowStepError(
            "选图清单没有完整覆盖所有镜头",
            {"expected_image_ids": sorted(expected_image_ids), "actual_image_ids": sorted(images or {})},
        )
    for image_id, image_path in images.items():
        if not Path(str(image_path)).resolve().is_file():
            raise WorkflowStepError(f"选图清单中的图片不存在：{image_id} -> {image_path}")
    for shot in shots:
        shot["image_path"] = str(Path(images[shot["id"]]).resolve())
        shot["frame_path"] = str(Path(images[shot["id"]]).resolve())
    return False, [str(shot["image_path"]) for shot in shots]


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

