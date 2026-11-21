"""开场动画：九张图依次翻页，最后一页缓慢放大到第一镜时长结束。音效在成片时叠加。"""

from __future__ import annotations

import shutil
from pathlib import Path

from ._constants import (
    CANVAS_SIZE,
    FPS,
    INTRO_RENDER_MIN_TIMEOUT_SECONDS,
    INTRO_RENDER_TIMEOUT_PER_SECOND,
    OUTPUT_HEIGHT,
    OUTPUT_SIZE,
    OUTPUT_WIDTH,
    PAGE_FLIP_COUNT,
    PAGE_FLIP_MIN_ZOOM_SECONDS,
    PAGE_FLIP_SECONDS,
    PAGE_FLIP_SFX_GAIN,
    PAGE_FLIP_ZOOM_TO,
    RESOLUTION,
    SHOT_CODEC,
    SHOT_CRF,
    SHOT_PIXEL_FORMAT,
    SHOT_PRESET,
)
from ._errors import (
    FFmpegNotFoundError,
    InvalidParameterError,
)
from ._ffmpeg import _probe, _run

__all__ = ["page_flip"]


def _fit_page(source: str, label: str) -> str:
    return (
        f"[{source}]scale={OUTPUT_SIZE}:force_original_aspect_ratio=increase:flags=lanczos,"
        f"crop={OUTPUT_SIZE},setsar=1,format={SHOT_PIXEL_FORMAT}[{label}]"
    )


def _timeline(duration: float, sfx_duration: float) -> tuple[list[float], list[float], float, float]:
    """按裁切后的翻页音效时长对齐：九次音效、八次翻页，最后一页放大时不再响。"""
    flips = PAGE_FLIP_COUNT - 1
    sfx = max(0.12, min(float(sfx_duration), 1.2))
    flip = min(PAGE_FLIP_SECONDS, max(0.10, sfx * 0.5))
    max_interval = max(0.12, (duration - PAGE_FLIP_MIN_ZOOM_SECONDS - flip) / flips)
    interval = min(sfx, max_interval)
    if interval < 0.12:
        interval = 0.12
        flip = min(flip, interval * 0.7)
    starts = [interval * (index + 1) for index in range(flips)]
    sfx_starts = [interval * index for index in range(PAGE_FLIP_COUNT)]
    land = min(starts[-1] + flip, duration - 0.05)
    return starts, sfx_starts, land, flip


def _slide_x(start: float, flip: float) -> str:
    progress = (
        f"min(1\\,max(0\\,(t-{start:.4f})/{flip:.4f}))"
    )
    return (
        f"if(lt(t\\,{start:.4f})\\,{OUTPUT_WIDTH}\\,"
        f"{OUTPUT_WIDTH}*(1-{progress}*{progress}*(3-2*{progress})))"
    )


def page_flip(
    image_paths: list[str | Path],
    output_path: str | Path,
    sfx_path: str | Path,
    *,
    duration: float,
) -> dict:
    """渲染首镜头画面：九张图翻页，最后一页放大；不含音轨。"""
    pages = [Path(path) for path in image_paths]
    if len(pages) != PAGE_FLIP_COUNT:
        raise InvalidParameterError(
            "image_paths",
            f"翻页开场必须正好 {PAGE_FLIP_COUNT} 张图，当前是 {len(pages)} 张",
        )
    missing = [str(path) for path in pages if not path.is_file()]
    if missing:
        raise InvalidParameterError("image_paths", f"翻页图片不存在：{missing[0]}")
    sfx_path = Path(sfx_path)
    if not sfx_path.is_file():
        raise InvalidParameterError(
            "sfx_path",
            f"翻页音效不存在：{sfx_path}。请把音效放到该路径（wav/mp3 均可，扩展名保持一致）",
        )
    try:
        duration = float(duration)
    except (TypeError, ValueError) as extra:
        raise InvalidParameterError("duration", "duration 必须是正数") from extra
    if duration <= 0:
        raise InvalidParameterError("duration", "必须传入大于 0 的 duration")
    output_path = Path(output_path)
    output_path.parent.mkdir(parents=True, exist_ok=True)

    ffmpeg = shutil.which("ffmpeg")
    if not ffmpeg:
        raise FFmpegNotFoundError("ffmpeg")

    sfx_duration = _probe(sfx_path)["duration"]
    flip_starts, sfx_starts, land, flip = _timeline(duration, sfx_duration)
    land_frame = max(0, round(land * FPS))
    total_frames = max(1, round(duration * FPS))
    zoom_frames = max(1, total_frames - land_frame)
    zoom_delta = PAGE_FLIP_ZOOM_TO - 1.0
    progress = (
        f"if(lt(on\\,{land_frame})\\,0\\,min(1\\,(on-{land_frame})/{zoom_frames}))"
    )
    zoom_expr = f"1+{zoom_delta:.4f}*{progress}*{progress}*(3-2*{progress})"

    command = [
        ffmpeg, "-y", "-hide_banner", "-nostats", "-loglevel", "error",
    ]
    for page in pages:
        command.extend([
            "-loop", "1", "-framerate", str(FPS),
            "-t", f"{duration:.6f}", "-i", str(page),
        ])
    chains = [_fit_page(f"{index}:v", f"p{index}") for index in range(PAGE_FLIP_COUNT - 1)]
    chains.append(
        f"[{PAGE_FLIP_COUNT - 1}:v]scale={OUTPUT_SIZE}:force_original_aspect_ratio=increase:flags=lanczos,"
        f"crop={OUTPUT_SIZE},setsar=1,format=yuv420p,"
        f"zoompan=z='{zoom_expr}':x='(iw-iw/zoom)/2':y='(ih-ih/zoom)/2':"
        f"d=1:s={OUTPUT_WIDTH}x{OUTPUT_HEIGHT}:fps={FPS},"
        f"format={SHOT_PIXEL_FORMAT}[p{PAGE_FLIP_COUNT - 1}]"
    )
    chains.append(
        f"color=c=black:size={CANVAS_SIZE}:r={FPS}:d={duration:.6f},"
        f"format={SHOT_PIXEL_FORMAT}[base]"
    )
    chains.append("[base][p0]overlay=0:0:eof_action=repeat[s0]")
    for index, start in enumerate(flip_starts, start=1):
        prev = f"s{index - 1}"
        current = f"s{index}" if index < PAGE_FLIP_COUNT - 1 else "video"
        chains.append(
            f"[{prev}][p{index}]overlay=x='{_slide_x(start, flip)}':y=0:"
            f"eof_action=repeat:enable='gte(t,{start:.4f})'[{current}]"
        )

    playable = [start for start in sfx_starts if start < duration]
    command.extend([
        "-filter_complex", ";".join(chains),
        "-map", "[video]", "-an",
        "-t", f"{duration:.6f}", "-r", str(FPS),
        "-c:v", SHOT_CODEC, "-preset", SHOT_PRESET, "-crf", str(SHOT_CRF),
        "-pix_fmt", SHOT_PIXEL_FORMAT,
        str(output_path),
    ])
    render_timeout = max(
        INTRO_RENDER_MIN_TIMEOUT_SECONDS,
        duration * INTRO_RENDER_TIMEOUT_PER_SECOND,
    )
    _run(command, "开场动画", timeout_seconds=render_timeout)

    return {
        "output_path": str(output_path),
        "duration": round(duration, 6),
        "fps": FPS,
        "resolution": RESOLUTION,
        "sfx": ["page_flip"] if playable else [],
        "opening_sfx": [
            {
                "path": str(sfx_path),
                "start": round(start, 6),
                "duration": round(min(sfx_duration, 0.5), 6),
                "gain": PAGE_FLIP_SFX_GAIN,
            }
            for start in playable
        ],
        "page_count": PAGE_FLIP_COUNT,
        "flip_starts": [round(item, 6) for item in flip_starts],
        "sfx_starts": [round(item, 6) for item in playable],
        "last_page_land": round(land, 6),
    }
