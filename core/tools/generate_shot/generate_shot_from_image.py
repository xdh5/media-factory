"""将图片按时长渲染为单镜头画面，不含音轨。"""

from __future__ import annotations

from pathlib import Path

from ._constants import (
    SHOT_FPS,
    SHOT_IMAGE_LOOP_PAD_SECONDS,
    SHOT_RENDER_MIN_TIMEOUT_SECONDS,
    SHOT_RENDER_TIMEOUT_PER_SECOND,
)
from ._errors import InvalidParameterError
from ._ffmpeg import _encode_video_args, _executable, _probe, _run, _validate_file
from ._filters import _motion_filter, _static_filter
from ._size import parse_size

__all__ = ["generate_shot_from_image"]


def generate_shot_from_image(
    image_path: str | Path,
    output_path: str | Path,
    *,
    size: str,
    duration: float,
    subtitle: str | None = None,
    subtitle_language: str = "zh",
    motion: dict | None = None,
) -> dict:
    """按时长渲染单镜头画面，不混合配音、BGM 或字幕。"""
    width, height = parse_size(size)
    image = _validate_file(image_path, "image_path")
    output = Path(output_path).resolve()
    if output.suffix.lower() != ".mp4":
        raise InvalidParameterError("output_path", "单镜头输出必须使用 .mp4 扩展名")
    try:
        effective_duration = float(duration)
    except (TypeError, ValueError) as extra:
        raise InvalidParameterError("duration", "duration 必须是正数") from extra
    if effective_duration <= 0:
        raise InvalidParameterError("duration", "必须传入大于 0 的 duration")

    ffmpeg = _executable("ffmpeg")
    output.parent.mkdir(parents=True, exist_ok=True)
    filters = (
        _motion_filter(motion, effective_duration, width, height)
        if motion else _static_filter(width, height)
    )
    image_loop_seconds = effective_duration + SHOT_IMAGE_LOOP_PAD_SECONDS
    command = [
        ffmpeg, "-y", "-hide_banner", "-nostats", "-loglevel", "error",
        "-loop", "1", "-framerate", str(SHOT_FPS),
        "-t", f"{image_loop_seconds:.6f}",
        "-i", str(image),
        "-vf", filters, "-map", "0:v:0",
        "-an",
        "-t", f"{effective_duration:.6f}",
        "-r", str(SHOT_FPS),
        *_encode_video_args(still_image=not bool(motion)),
        str(output),
    ]
    render_timeout = max(
        SHOT_RENDER_MIN_TIMEOUT_SECONDS,
        effective_duration * SHOT_RENDER_TIMEOUT_PER_SECOND,
    )
    _run(command, "单镜头渲染", timeout_seconds=render_timeout)

    result_probe = _probe(output)
    return {
        "output_path": str(output),
        "duration": round(result_probe["duration"], 6),
        "actual_duration": round(result_probe["duration"], 6),
        "duration_source": "duration",
        "has_audio": False,
        "has_subtitle": bool(subtitle is not None and str(subtitle).strip()),
        "has_motion": bool(motion),
    }
