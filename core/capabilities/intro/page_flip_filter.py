"""开场动画：九张图依次翻页，翻页播音效，最后一页缓慢放大到第一句旁白结束。"""

from __future__ import annotations

import shutil
import subprocess
from pathlib import Path

from core.capabilities.intro._constants import (
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
)
from core.capabilities.intro._errors import (
    FFMPEGNotFoundError,
    InvalidParameterError,
    RenderError,
    RenderTimeoutError,
)
from core.tools.video._constants import (
    VIDEO_AUDIO_CHANNELS,
    VIDEO_AUDIO_CODEC,
    VIDEO_AUDIO_RATE,
    VIDEO_CODEC,
    VIDEO_CRF,
    VIDEO_PIXEL_FORMAT,
    VIDEO_PRESET,
)
from core.tools.video.render_shot import _probe

__all__ = ["page_flip"]


def _run(command: list[str], timeout_seconds: float) -> None:
    try:
        completed = subprocess.run(
            command,
            check=False,
            capture_output=True,
            text=True,
            encoding="utf-8",
            errors="replace",
            timeout=timeout_seconds,
        )
    except subprocess.TimeoutExpired as exc:
        raise RenderTimeoutError(timeout_seconds) from exc
    if completed.returncode != 0:
        details = completed.stderr.strip() or completed.stdout.strip()
        raise RenderError(details[-2000:] or "FFmpeg 渲染失败")


def _fit_page(source: str, label: str) -> str:
    return (
        f"[{source}]scale={OUTPUT_SIZE}:force_original_aspect_ratio=increase:flags=lanczos,"
        f"crop={OUTPUT_SIZE},setsar=1,format={VIDEO_PIXEL_FORMAT}[{label}]"
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
    tts_path: str | Path,
    output_path: str | Path,
    sfx_path: str | Path,
    *,
    audio_start: float = 0,
    audio_end: float | None = None,
) -> dict:
    """渲染首镜头：九张图翻页，最后一页放大至第一句旁白结束。"""
    pages = [Path(path) for path in image_paths]
    if len(pages) != PAGE_FLIP_COUNT:
        raise InvalidParameterError(
            "image_paths",
            f"翻页开场必须正好 {PAGE_FLIP_COUNT} 张图，当前是 {len(pages)} 张",
        )
    missing = [str(path) for path in pages if not path.is_file()]
    if missing:
        raise InvalidParameterError("image_paths", f"翻页图片不存在：{missing[0]}")
    tts_path = Path(tts_path)
    if not tts_path.is_file():
        raise InvalidParameterError("tts_path", f"TTS 文件不存在：{tts_path}")
    sfx_path = Path(sfx_path)
    if not sfx_path.is_file():
        raise InvalidParameterError(
            "sfx_path",
            f"翻页音效不存在：{sfx_path}。请把音效放到该路径（wav/mp3 均可，扩展名保持一致）",
        )
    tts_duration = _probe(tts_path)["duration"]
    try:
        effective_start = float(audio_start)
        effective_end = float(audio_end) if audio_end is not None else tts_duration
    except (TypeError, ValueError) as exc:
        raise InvalidParameterError("audio_start/audio_end", "音频起止时间必须是数字") from exc
    if effective_start < 0 or effective_end <= effective_start:
        raise InvalidParameterError("audio_start/audio_end", "必须满足 0 ≤ audio_start < audio_end")
    if effective_end > tts_duration + 0.01:
        raise InvalidParameterError(
            "audio_end",
            f"audio_end={effective_end:.6f} 超过 TTS 真实时长 {tts_duration:.6f}",
        )
    effective_end = min(effective_end, tts_duration)
    duration = effective_end - effective_start
    output_path = Path(output_path)
    output_path.parent.mkdir(parents=True, exist_ok=True)

    ffmpeg = shutil.which("ffmpeg")
    if not ffmpeg:
        raise FFMPEGNotFoundError(
            "未找到 ffmpeg，请先安装并加入 PATH（如 winget install Gyan.FFmpeg）",
        )

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
    command.extend([
        "-ss", f"{effective_start:.6f}", "-t", f"{duration:.6f}", "-i", str(tts_path),
        "-i", str(sfx_path),
    ])
    tts_index = PAGE_FLIP_COUNT
    sfx_index = PAGE_FLIP_COUNT + 1

    chains = [_fit_page(f"{index}:v", f"p{index}") for index in range(PAGE_FLIP_COUNT - 1)]
    chains.append(
        f"[{PAGE_FLIP_COUNT - 1}:v]scale={OUTPUT_SIZE}:force_original_aspect_ratio=increase:flags=lanczos,"
        f"crop={OUTPUT_SIZE},setsar=1,format=yuv420p,"
        f"zoompan=z='{zoom_expr}':x='(iw-iw/zoom)/2':y='(ih-ih/zoom)/2':"
        f"d=1:s={OUTPUT_WIDTH}x{OUTPUT_HEIGHT}:fps={FPS},"
        f"format={VIDEO_PIXEL_FORMAT}[p{PAGE_FLIP_COUNT - 1}]"
    )
    chains.append(
        f"color=c=black:size={CANVAS_SIZE}:r={FPS}:d={duration:.6f},"
        f"format={VIDEO_PIXEL_FORMAT}[base]"
    )
    chains.append("[base][p0]overlay=0:0:eof_action=repeat[s0]")
    for index, start in enumerate(flip_starts, start=1):
        prev = f"s{index - 1}"
        current = f"s{index}" if index < PAGE_FLIP_COUNT - 1 else "video"
        chains.append(
            f"[{prev}][p{index}]overlay=x='{_slide_x(start, flip)}':y=0:"
            f"eof_action=repeat:enable='gte(t,{start:.4f})'[{current}]"
        )

    chains.append(
        f"[{tts_index}:a]atrim=0:{duration:.6f},asetpts=PTS-STARTPTS,"
        f"aresample={VIDEO_AUDIO_RATE},aformat=channel_layouts=stereo[tts]"
    )
    mix_labels = ["[tts]"]
    sfx_used = False
    playable = [start for start in sfx_starts if start < duration]
    if playable:
        sfx_used = True
        labels = "".join(f"[sfx{index}]" for index in range(len(playable)))
        chains.append(
            f"[{sfx_index}:a]aresample={VIDEO_AUDIO_RATE},aformat=channel_layouts=stereo,"
            f"volume={PAGE_FLIP_SFX_GAIN:.3f},asplit={len(playable)}{labels}"
        )
        delayed = []
        for index, start in enumerate(playable):
            delay_ms = round(start * 1000)
            chains.append(
                f"[sfx{index}]adelay={delay_ms}:all=1[flip{index}]"
            )
            delayed.append(f"[flip{index}]")
        if len(delayed) == 1:
            chains.append(f"{delayed[0]}anull[flips]")
        else:
            chains.append(
                "".join(delayed)
                + f"amix=inputs={len(delayed)}:duration=longest:normalize=0,atrim=0:{duration:.6f},"
                f"asetpts=PTS-STARTPTS[flips]"
            )
        mix_labels.append("[flips]")
    chains.append(
        "".join(mix_labels)
        + f"amix=inputs={len(mix_labels)}:duration=first:normalize=0[audio]"
    )

    command.extend([
        "-filter_complex", ";".join(chains),
        "-map", "[video]", "-map", "[audio]",
        "-t", f"{duration:.6f}", "-r", str(FPS),
        "-c:v", VIDEO_CODEC, "-preset", VIDEO_PRESET, "-crf", str(VIDEO_CRF),
        "-pix_fmt", VIDEO_PIXEL_FORMAT,
        "-c:a", VIDEO_AUDIO_CODEC, "-ar", str(VIDEO_AUDIO_RATE), "-ac", str(VIDEO_AUDIO_CHANNELS),
        "-movflags", "+faststart", str(output_path),
    ])
    render_timeout = max(
        INTRO_RENDER_MIN_TIMEOUT_SECONDS,
        duration * INTRO_RENDER_TIMEOUT_PER_SECOND,
    )
    _run(command, render_timeout)

    return {
        "output_path": str(output_path),
        "duration": round(duration, 6),
        "fps": FPS,
        "resolution": RESOLUTION,
        "sfx": ["page_flip"] if sfx_used else [],
        "audio_start": round(effective_start, 6),
        "audio_end": round(effective_end, 6),
        "page_count": PAGE_FLIP_COUNT,
        "flip_starts": [round(item, 6) for item in flip_starts],
        "last_page_land": round(land, 6),
    }
