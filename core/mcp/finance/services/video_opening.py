"""财经片头渲染和缓存。"""

from __future__ import annotations

import hashlib
import json
import random
from pathlib import Path
from core.tools.generate_shot import INTRO_RENDERER_VERSION, SFX_SHUTTER_GAIN, SFX_SHUTTER_PATH, SFX_SHUTTER_SECONDS, SFX_ALERT_GAIN, SFX_ALERT_PATH, SFX_ALERT_SECONDS, SHUTTER_START_SECONDS, ShotToolError, generate_shot_from_intro
from ..config.settings import MCP_ID
from ..errors import WorkflowStepError


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
        pool = [
            str(item.get("image_path") or item.get("frame_path") or "")
            for item in shots
        ]
        pool = [path for path in pool if path]
        seed = "|".join([MCP_ID, shot["id"]] + [_hash_file(path) for path in pool])
        page_images = _pick_page_flip_images(pool, shot["image_path"], seed)
    metadata_path = segment_path.with_suffix(".json")
    follow_video = ""
    if len(shots) > 1:
        follow_video = str(shots[1].get("segment_path") or "").strip()
    payload = {
        "version": 5,
        "intro": intro,
        "intro_renderer_version": INTRO_RENDERER_VERSION,
        "image_sha256": _hash_file(shot["image_path"]),
        "follow_video_sha256": _hash_file(follow_video) if follow_video else "",
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
            video_path=follow_video or None,
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

