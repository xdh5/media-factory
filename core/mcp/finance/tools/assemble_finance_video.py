"""财经成片：封面、片头镜头与最终合成。"""

from __future__ import annotations

import hashlib
import json
import random
from datetime import datetime, timezone
from pathlib import Path

from core.tools.generate_cover_image import CoverError, generate_cover_image
from core.tools.generate_final_video import generate_final_video, safe_filename
from core.tools.generate_shot import (
    INTRO_RENDERER_VERSION,
    SFX_SHUTTER_GAIN,
    SFX_SHUTTER_PATH,
    SFX_SHUTTER_SECONDS,
    SFX_ALERT_GAIN,
    SFX_ALERT_PATH,
    SFX_ALERT_SECONDS,
    SHUTTER_START_SECONDS,
    ShotToolError,
    generate_shot_from_intro,
    intro_bgm_start_seconds,
)

from .._constants import (
    MATRIXMEDIA_AI_CREATIVE_STATEMENT,
    MCP_ID,
    STORYBOARD_TEXT_FILE_NAME,
    TOPIC_DEDUPLICATION_DAYS,
    VIDEO_SIZE,
)
from .._errors import WorkflowStepError
from .narration import display_subtitle_cue, display_subtitle_text
from .save_draft import load_draft
from .storyboard import load_prepared_tts, parse_storyboard


def _production_config(config: dict) -> dict:
    bgm_path = str(config.get("bgm_path") or "").strip()
    intro = str(config.get("intro") or "").strip()
    account_group = str(config.get("matrixmedia_account_group") or "").strip()
    if not bgm_path:
        raise WorkflowStepError("production_config.bgm_path 不能为空")
    if not intro:
        raise WorkflowStepError("production_config.intro 不能为空")
    if not account_group:
        raise WorkflowStepError("production_config.matrixmedia_account_group 不能为空")
    try:
        cover_frame_seconds = float(config.get("cover_frame_seconds"))
    except (TypeError, ValueError) as exc:
        raise WorkflowStepError("production_config.cover_frame_seconds 必须是数字") from exc
    stickers = config.get("shot_stickers")
    if not isinstance(stickers, list) or not stickers:
        raise WorkflowStepError("production_config.shot_stickers 必须是非空列表")
    return {
        "bgm_path": Path(bgm_path),
        "intro": intro,
        "intro_sfx_path": Path(str(config["intro_sfx_path"])) if config.get("intro_sfx_path") else None,
        "cover_frame_seconds": cover_frame_seconds,
        "shot_stickers": tuple(str(item) for item in stickers),
        "matrixmedia_account_group": account_group,
    }


def _with_display_text(shots: list[dict]) -> list[dict]:
    prepared: list[dict] = []
    for shot in shots:
        item = dict(shot)
        if item.get("subtitle") is not None:
            item["subtitle"] = display_subtitle_text(str(item.get("subtitle") or ""))
        lines = item.get("subtitle_lines")
        if isinstance(lines, list):
            cleaned = []
            for line in lines:
                if not isinstance(line, dict):
                    continue
                row = dict(line)
                try:
                    cue = display_subtitle_cue(str(row.get("text") or ""))
                except ValueError as extra:
                    raise WorkflowStepError(f"镜头 {item.get('id')} 字幕重点标记无效：{extra}") from extra
                row["text"] = cue
                cleaned.append(row)
            item["subtitle_lines"] = cleaned
        prepared.append(item)
    return prepared


def _hash_file(path: str | Path) -> str:
    digest = hashlib.sha256()
    with Path(path).open("rb") as source:
        for chunk in iter(lambda: source.read(1024 * 1024), b""):
            digest.update(chunk)
    return digest.hexdigest()


def _resolve_intro_sfx(path: Path | None) -> Path | None:
    if path is None:
        return None
    if path.is_file():
        return path
    parent = path.parent
    stem = path.stem
    for suffix in (".wav", ".mp3", ".m4a", ".aac", ".ogg"):
        candidate = parent / f"{stem}{suffix}"
        if candidate.is_file():
            return candidate
    return path


def _pick_page_flip_images(image_paths: list[str], last_path: str, seed: str) -> list[str]:
    resolved = [str(Path(path).resolve()) for path in image_paths]
    last = str(Path(last_path).resolve())
    others = [path for path in resolved if path != last]
    pool = others or resolved
    rng = random.Random(int(hashlib.sha256(seed.encode("utf-8")).hexdigest()[:16], 16))
    pages: list[str] = []
    for _ in range(8):
        choices = [path for path in pool if not pages or path != pages[-1]] or pool
        pages.append(rng.choice(choices))
    pages.append(last)
    return pages


def _slide_in_opening_sfx() -> list[dict]:
    items = []
    if SFX_ALERT_PATH.is_file():
        items.append({
            "path": str(SFX_ALERT_PATH),
            "start": 0.0,
            "duration": SFX_ALERT_SECONDS,
            "gain": SFX_ALERT_GAIN,
        })
    if SFX_SHUTTER_PATH.is_file():
        items.append({
            "path": str(SFX_SHUTTER_PATH),
            "start": SHUTTER_START_SECONDS,
            "duration": SFX_SHUTTER_SECONDS,
            "gain": SFX_SHUTTER_GAIN,
        })
    return items


def _render_first_shot_cached(
    intro: str,
    intro_sfx_path: Path | None,
    shots: list[dict],
    shot: dict,
    segment_path: Path,
    *,
    force: bool,
) -> tuple[bool, list[dict]]:
    page_images: list[str] = []
    sfx_path = _resolve_intro_sfx(intro_sfx_path)
    if intro == "page_flip":
        pool = [str(item["image_path"]) for item in shots]
        seed = "|".join([MCP_ID, shot["id"]] + [_hash_file(path) for path in pool])
        page_images = _pick_page_flip_images(pool, shot["image_path"], seed)
    metadata_path = segment_path.with_suffix(".json")
    payload = {
        "version": 4,
        "intro": intro,
        "intro_renderer_version": INTRO_RENDERER_VERSION,
        "image_sha256": _hash_file(shot["image_path"]),
        "page_image_sha256": [_hash_file(path) for path in page_images],
        "sfx_sha256": _hash_file(sfx_path) if intro == "page_flip" and sfx_path and sfx_path.is_file() else None,
        "alert_sha256": _hash_file(SFX_ALERT_PATH) if intro == "slide_in_shutter" and SFX_ALERT_PATH.is_file() else None,
        "duration": shot["duration"],
        "motion": shot["motion"],
    }
    signature = hashlib.sha256(
        json.dumps(payload, ensure_ascii=False, sort_keys=True, separators=(",", ":")).encode("utf-8")
    ).hexdigest()
    if not force and segment_path.is_file() and metadata_path.is_file():
        try:
            metadata = json.loads(metadata_path.read_text(encoding="utf-8"))
            if metadata.get("signature") == signature:
                opening_sfx = list(metadata.get("opening_sfx") or [])
                if not opening_sfx and intro == "slide_in_shutter":
                    opening_sfx = _slide_in_opening_sfx()
                return True, opening_sfx
        except (OSError, ValueError, json.JSONDecodeError):
            pass
    try:
        if intro == "page_flip" and (sfx_path is None or not Path(sfx_path).is_file()):
            raise WorkflowStepError("片头音效不存在，请在 production_config.intro_sfx_path 指向实际文件")
        rendered = generate_shot_from_intro(
            intro,
            segment_path,
            duration=shot["duration"],
            image_path=shot["image_path"],
            image_paths=page_images or None,
            sfx_path=sfx_path,
            motion=shot["motion"],
        )
    except ShotToolError as extra:
        raise WorkflowStepError(extra.message, extra.details) from extra
    opening_sfx = list(rendered.get("opening_sfx") or [])
    temporary = metadata_path.with_suffix(".json.tmp")
    temporary.write_text(
        json.dumps(
            {"signature": signature, "shot_id": shot["id"], "opening_sfx": opening_sfx},
            ensure_ascii=False,
            sort_keys=True,
        ),
        encoding="utf-8",
    )
    temporary.replace(metadata_path)
    return False, opening_sfx


def _storyboard_hash(value: str) -> str:
    return hashlib.sha256(value.encode("utf-8")).hexdigest()


def _load_saved_storyboard(
    image_metadata: dict,
    cache_root: Path,
    storyboard_text: str | None,
) -> str:
    saved = str(image_metadata.get("storyboard_text") or "").strip()
    saved_path = Path(str(image_metadata.get("storyboard_path") or "")).resolve()
    if not saved and saved_path.is_file():
        saved = saved_path.read_text(encoding="utf-8").strip()
    fallback_path = cache_root / STORYBOARD_TEXT_FILE_NAME
    if not saved and fallback_path.is_file():
        saved = fallback_path.read_text(encoding="utf-8").strip()
    if saved:
        expected_hash = str(image_metadata.get("storyboard_sha256") or "").strip()
        if expected_hash and _storyboard_hash(saved) != expected_hash:
            raise WorkflowStepError(
                "已保存的分镜文本损坏，请重新调用 finance_prepare_images",
                {"storyboard_sha256": expected_hash},
            )
        return saved
    fallback = str(storyboard_text or "").strip()
    if not fallback:
        raise WorkflowStepError(
            "生图清单里没有分镜文本。请重新调用 finance_prepare_images，出片不必再传 storyboard_text"
        )
    expected_hash = str(image_metadata.get("storyboard_sha256") or "").strip()
    if expected_hash and _storyboard_hash(fallback) != expected_hash:
        raise WorkflowStepError(
            "传入的 storyboard_text 与生图时不一致。请重新调用 finance_prepare_images 后直接 finance_finish_video",
            {"storyboard_sha256": expected_hash, "received_sha256": _storyboard_hash(fallback)},
        )
    return fallback


def finish_finance_video(
    draft_path: str | Path,
    *,
    image_manifest_path: str | Path,
    production_config: dict,
    storyboard_text: str | None = None,
    force_shot_ids: list[str] | None = None,
    progress=None,
) -> dict:
    settings = _production_config(production_config)
    resolved_draft, draft = load_draft(draft_path, "财经稿件")
    required_draft_fields = {
        "topic", "run_id", "topic_record_id", "article", "title", "short_title",
        "hashtags", "cache_dir", "output_dir",
    }
    missing_fields = sorted(required_draft_fields.difference(draft))
    if missing_fields:
        raise WorkflowStepError(
            f"财经稿件缺少字段：{missing_fields}",
            {"draft_path": str(resolved_draft)},
        )
    record = {"id": draft["topic_record_id"], "topic": draft["topic"]}
    run_id = str(draft["run_id"])
    article = str(draft["article"])
    metadata = {
        "title": str(draft["title"]),
        "short_title": str(draft["short_title"]),
        "hashtags": list(draft["hashtags"]),
        "cover_lines": list(draft.get("cover_lines") or [str(draft["title"])]),
        "cover_highlights": list(draft.get("cover_highlights") or [str(draft["title"])]),
    }
    cache_root = Path(draft["cache_dir"]).resolve()
    output_root = Path(draft["output_dir"]).resolve()
    cache_root.mkdir(parents=True, exist_ok=True)
    output_root.mkdir(parents=True, exist_ok=True)

    tts = load_prepared_tts(cache_root)
    tts_path = tts["tts_path"]
    resolved_image_manifest = Path(image_manifest_path).resolve()
    if not resolved_image_manifest.is_file():
        raise WorkflowStepError(f"选图清单不存在：{resolved_image_manifest}")
    try:
        image_manifest = json.loads(resolved_image_manifest.read_text(encoding="utf-8"))
    except (OSError, json.JSONDecodeError) as exc:
        raise WorkflowStepError(f"读取选图清单失败：{resolved_image_manifest}。{exc}") from exc
    image_metadata = image_manifest.get("metadata")
    if not isinstance(image_metadata, dict):
        raise WorkflowStepError("选图清单缺少 metadata")
    if Path(str(image_metadata.get("draft_path") or "")).resolve() != resolved_draft:
        raise WorkflowStepError("选图清单不属于当前稿件，请重新调用 finance_prepare_images")
    storyboard_output = _load_saved_storyboard(image_metadata, cache_root, storyboard_text)
    shots = parse_storyboard(storyboard_output, tts["timeline"])
    images = image_manifest.get("images")
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
    try:
        cover = generate_cover_image(
            [shot["image_path"] for shot in shots],
            metadata["title"],
            cache_root / "cover.png",
            size=VIDEO_SIZE,
            lines=metadata["cover_lines"],
            highlighted_words=metadata["cover_highlights"],
        )
    except CoverError as exc:
        raise WorkflowStepError(exc.message, exc.details) from exc

    forced = set(force_shot_ids or [])
    unknown_forced = forced.difference(shot["id"] for shot in shots)
    if unknown_forced:
        raise WorkflowStepError(f"要重做的镜头不存在：{sorted(unknown_forced)}")
    segment_dir = cache_root / "segments"
    segment_dir.mkdir(parents=True, exist_ok=True)
    first_shot = shots[0]
    first_segment = segment_dir / f"{first_shot['id']}.mp4"
    first_shot["cache_hit"], opening_sfx = _render_first_shot_cached(
        settings["intro"],
        settings["intro_sfx_path"],
        shots,
        first_shot,
        first_segment,
        force=first_shot["id"] in forced,
    )
    video_shots = [{
        "id": first_shot["id"],
        "segment_path": str(first_segment),
        "subtitle": first_shot["subtitle"],
        "subtitle_lines": first_shot.get("subtitle_lines") or [],
    }]
    video_shots.extend(
        {
            "id": shot["id"],
            "image_path": shot["image_path"],
            "duration": shot["duration"],
            "subtitle": shot["subtitle"],
            "subtitle_lines": shot.get("subtitle_lines") or [],
            "motion": shot["motion"],
        }
        for shot in shots[1:]
    )
    try:
        final_result = generate_final_video(
            _with_display_text(video_shots),
            output_root / f"{safe_filename(metadata['title'])}.mp4",
            cache_root / "shot-cache",
            size=VIDEO_SIZE,
            tts_path=tts_path,
            cover_path=cover["output_path"],
            cover_duration=settings["cover_frame_seconds"],
            bgm_path=settings["bgm_path"],
            bgm_start_seconds=intro_bgm_start_seconds(
                settings["intro"],
                first_shot_duration=float(first_shot["duration"]),
            ),
            stickers=list(settings["shot_stickers"]),
            force_shot_ids=[shot_id for shot_id in forced if shot_id != first_shot["id"]],
            opening_sfx=opening_sfx,
            progress=progress,
        )
    except Exception as extra:
        raise WorkflowStepError(f"财经成片失败：{extra}") from extra
    final_path = Path(final_result["output_path"])

    publish_copy = "【" + metadata["short_title"] + " " + " ".join(
        f"#{tag.lstrip('#')}" for tag in metadata["hashtags"]
    ) + "】"
    title_path = output_root / "title.txt"
    short_title_path = output_root / "short-title.txt"
    publish_copy_path = output_root / "publish-copy.txt"
    title_path.write_text(metadata["title"] + "\n", encoding="utf-8")
    short_title_path.write_text(metadata["short_title"] + "\n", encoding="utf-8")
    publish_copy_path.write_text(publish_copy + "\n", encoding="utf-8")

    created_at = datetime.now(timezone.utc).isoformat(timespec="seconds").replace("+00:00", "Z")
    manifest = {
        "status": "awaiting_publish_confirmation",
        "confirmation_required": "publish",
        "line": MCP_ID,
        "topic": record["topic"],
        "run_id": run_id,
        "article": article,
        **metadata,
        "cover_path": cover["output_path"],
        "video_path": str(final_path),
        "cache_dir": str(cache_root),
        "output_dir": str(output_root),
        "title_path": str(title_path),
        "short_title_path": str(short_title_path),
        "publish_bt2": metadata["short_title"],
        "publish_copy": publish_copy,
        "publish_copy_path": str(publish_copy_path),
        "matrixmedia_account_group": settings["matrixmedia_account_group"],
        "creativeStatement": MATRIXMEDIA_AI_CREATIVE_STATEMENT,
        "created_at": created_at,
        "topic_record_id": record["id"],
        "database_commit": {
            "workflow": MCP_ID,
            "publication_id": f"{MCP_ID}:{run_id}",
            "run_id": run_id,
            "topic": record["topic"],
            "days": TOPIC_DEDUPLICATION_DAYS,
            "entries": [],
        },
        "shots": shots,
    }
    manifest_path = cache_root / "manifest.json"
    manifest["manifest_path"] = str(manifest_path)
    manifest_path.write_text(json.dumps(manifest, ensure_ascii=False, indent=2), encoding="utf-8")
    return manifest
