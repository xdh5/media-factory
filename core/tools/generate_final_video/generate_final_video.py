"""拼镜头后合配音；字幕、贴纸、BGM、封面均可选。"""

from __future__ import annotations

from pathlib import Path
from typing import Callable
from uuid import uuid4

from core.tools.generate_sticker import generate_sticker
from core.tools.generate_subtitles import generate_subtitles

from ._compose_shots import compose_shots
from ._mix_body import mix_body
from ._errors import InvalidParameterError
from ._ffmpeg import _encode_video_args, _executable, _probe, _run
from ._size import parse_size

__all__ = ["generate_final_video"]

ProgressCallback = Callable[[str], None]


def _normalize_composed_video(source_path: str | Path, output_path: Path) -> str:
    """把 copy concat 的细小时间戳漂移规范为恒定30帧，避免多路叠加时卡在镜头边界。"""
    source = Path(source_path).resolve()
    probe = _probe(source)
    temporary = output_path.with_name(f".{output_path.stem}-{uuid4().hex}.tmp.mp4")
    command = [
        _executable("ffmpeg"), "-y", "-i", str(source),
        "-an", "-fps_mode", "cfr", "-r", "30",
        *_encode_video_args(still_image=False),
        "-movflags", "+faststart", str(temporary),
    ]
    try:
        _run(command, "规范化镜头时间戳", timeout_seconds=max(600, probe["duration"] * 15))
        _probe(temporary)
        temporary.replace(output_path)
    finally:
        temporary.unlink(missing_ok=True)
    return str(output_path)


def _compose_item(shot: dict) -> dict:
    item = {"id": shot["id"]}
    segment = str(shot.get("segment_path") or "").strip()
    if segment:
        item["segment_path"] = segment
        return item
    item["image_path"] = shot["image_path"]
    for key in ("duration", "motion"):
        if shot.get(key) is not None:
            item[key] = shot[key]
    return item


def _subtitle_cues(shots: list[dict], shot_results: list[dict]) -> list[dict]:
    by_id = {str(shot.get("id") or "").strip(): shot for shot in shots}
    cues: list[dict] = []
    cursor = 0.0
    for result in shot_results:
        source = by_id.get(str(result["id"])) or {}
        duration = float(result.get("duration") or 0)
        language = str(source.get("subtitle_language") or "zh")
        lines = source.get("subtitle_lines")
        if isinstance(lines, list) and lines:
            for item in lines:
                if not isinstance(item, dict):
                    continue
                text = item.get("text")
                if isinstance(text, list):
                    if not text:
                        continue
                else:
                    text = str(text or "").strip()
                    if not text:
                        continue
                start = cursor + max(0.0, float(item.get("start") or 0))
                end = cursor + min(duration, float(item.get("end") or duration))
                if end <= start:
                    end = min(cursor + duration, start + 0.08)
                cues.append({
                    "start": round(start, 3),
                    "end": round(end, 3),
                    "text": text,
                    "language": language,
                })
        else:
            text = str(source.get("subtitle") or "").strip()
            if text:
                cues.append({
                    "start": cursor,
                    "end": cursor + duration,
                    "text": text,
                    "language": language,
                })
        cursor += duration
    return cues


def _sticker_overlays(names: list[str] | tuple[str, ...] | None, cache_root: Path, width: int, height: int) -> list[dict]:
    overlays: list[dict] = []
    for index, name in enumerate(names or ()):
        sticker = str(name or "").strip()
        if not sticker:
            continue
        overlays.append(
            generate_sticker(
                sticker,
                cache_root / f"sticker-{index:02d}-{sticker}.mov",
                width,
                height,
            )
        )
    return overlays


def generate_final_video(
    shots: list[dict],
    output_path: str | Path,
    cache_dir: str | Path,
    *,
    size: str,
    tts_path: str | Path,
    bgm_path: str | Path | None = None,
    cover_path: str | Path | None = None,
    cover_duration: float | None = None,
    stickers: list[str] | tuple[str, ...] | None = None,
    force_shot_ids: list[str] | None = None,
    opening_sfx: list[dict] | None = None,
    bgm_start_seconds: float | None = None,
    subtitle_style: dict | None = None,
    subtitle_position: dict | None = None,
    extra_ass_paths: list[str | Path] | None = None,
    normalize_composed: bool = False,
    progress: ProgressCallback | None = None,
) -> dict:
    """先拼无音镜头，再一次叠配音、BGM、字幕、贴纸和封面。"""
    if not isinstance(shots, list) or not shots:
        raise InvalidParameterError("shots", "shots 必须是至少一个镜头")
    cache_root = Path(cache_dir).resolve()
    cache_root.mkdir(parents=True, exist_ok=True)
    destination = Path(output_path).resolve()
    destination.parent.mkdir(parents=True, exist_ok=True)

    if progress:
        progress("正在渲染镜头")
    composed = compose_shots(
        [_compose_item(shot) for shot in shots],
        cache_root / "composed.mp4",
        cache_root / "shots",
        size=size,
        force_shot_ids=force_shot_ids,
        progress=progress,
    )
    body_video_path = composed["output_path"]
    if normalize_composed:
        if progress:
            progress("正在规范化镜头时间戳")
        body_video_path = _normalize_composed_video(
            composed["output_path"],
            cache_root / "composed-normalized.mp4",
        )
    width, height = parse_size(size)
    cues = _subtitle_cues(shots, composed["shots"])
    overlays = _sticker_overlays(stickers, cache_root, width, height)
    ass_path = None
    fontsdir = None
    if cues:
        subtitles = generate_subtitles(
            cues,
            cache_root / "timeline.ass",
            width,
            height,
            style=subtitle_style,
            position=subtitle_position,
        )
        ass_path = subtitles["output_path"]
        fontsdir = subtitles["fontsdir"]
    if progress:
        progress("正在合成配音与字幕")
    body = mix_body(
        body_video_path,
        destination,
        tts_path=tts_path,
        bgm_path=None if bgm_path is None else (str(bgm_path).strip() or None),
        ass_path=ass_path,
        extra_ass_paths=extra_ass_paths,
        fontsdir=fontsdir,
        overlays=overlays or None,
        cover_path=str(cover_path or "").strip() or None,
        cover_duration=cover_duration,
        opening_sfx=opening_sfx,
        bgm_start_seconds=bgm_start_seconds,
    )
    return {
        "output_path": body["output_path"],
        "duration": body["duration"],
        "body_duration": composed["duration"],
        "shot_count": composed["shot_count"],
    }
