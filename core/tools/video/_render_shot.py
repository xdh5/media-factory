"""将图片、可选语音、字幕和镜头动效合成为单个镜头。"""

from __future__ import annotations

import json
import re
import shutil
import subprocess
import tempfile
import unicodedata
from pathlib import Path

from ._constants import (
    SUBTITLE_FONT_DIRECTORIES,
    SUBTITLE_MAX_LINES,
    VIDEO_AUDIO_CHANNELS,
    VIDEO_AUDIO_CODEC,
    VIDEO_AUDIO_RATE,
    VIDEO_CODEC,
    VIDEO_CRF,
    VIDEO_FPS,
    VIDEO_MOTION_SUPERSAMPLE,
    VIDEO_PIXEL_FORMAT,
    VIDEO_PROBE_TIMEOUT_SECONDS,
    VIDEO_PRESET,
    VIDEO_RENDER_MIN_TIMEOUT_SECONDS,
    VIDEO_RENDER_TIMEOUT_PER_SECOND,
)
from ._errors import (
    FFmpegNotFoundError,
    InvalidParameterError,
    MediaFileNotFoundError,
    MediaProbeError,
    RenderError,
    RenderTimeoutError,
)
from ._select_subtitle import _parse_size, _select_subtitle


def _executable(name: str) -> str:
    executable = shutil.which(name)
    if not executable:
        raise FFmpegNotFoundError(name)
    return executable


def _run(command: list[str], context: str, *, timeout_seconds: float) -> None:
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
        raise RenderTimeoutError(context, timeout_seconds) from exc
    if completed.returncode != 0:
        detail = (completed.stderr or completed.stdout or "").strip()[-3000:]
        raise RenderError(f"{context}：{detail or '未知 FFmpeg 错误'}")


def _probe(path: Path) -> dict:
    ffprobe = _executable("ffprobe")
    try:
        completed = subprocess.run(
            [
                ffprobe,
                "-v", "error",
                "-show_entries", "format=duration:stream=codec_type,width,height",
                "-of", "json",
                str(path),
            ],
            check=False,
            capture_output=True,
            text=True,
            encoding="utf-8",
            errors="replace",
            timeout=VIDEO_PROBE_TIMEOUT_SECONDS,
        )
    except subprocess.TimeoutExpired as exc:
        raise MediaProbeError(
            f"读取媒体信息超过 {VIDEO_PROBE_TIMEOUT_SECONDS} 秒：{path}"
        ) from exc
    try:
        payload = json.loads(completed.stdout or "{}")
        duration = float((payload.get("format") or {}).get("duration") or 0)
    except (TypeError, ValueError, json.JSONDecodeError) as exc:
        raise MediaProbeError(f"无法读取媒体信息：{path}") from exc
    if completed.returncode != 0 or duration <= 0:
        detail = (completed.stderr or "").strip()[-1200:]
        raise MediaProbeError(f"无法读取媒体时长：{path}。{detail}")
    return {"duration": duration, "streams": payload.get("streams") or []}


def _validate_file(value: str | Path, parameter: str) -> Path:
    path = Path(value).resolve()
    if not path.is_file():
        raise MediaFileNotFoundError(parameter, str(path))
    return path


def _ass_time(seconds: float) -> str:
    centiseconds = max(0, round(seconds * 100))
    hours, centiseconds = divmod(centiseconds, 360_000)
    minutes, centiseconds = divmod(centiseconds, 6_000)
    secs, centiseconds = divmod(centiseconds, 100)
    return f"{hours}:{minutes:02d}:{secs:02d}.{centiseconds:02d}"


def _unit_width(value: str) -> int:
    return 2 if unicodedata.east_asian_width(value) in {"W", "F"} else 1


def _wrap_text(value: str, max_width: int) -> str:
    cleaned = " ".join(str(value or "").replace("\r", " ").replace("\n", " ").split())
    tokens = re.findall(r"[A-Za-z0-9]+(?:['’.-][A-Za-z0-9]+)*|\s+|.", cleaned)
    lines: list[str] = []
    current = ""
    width = 0
    for token in tokens:
        if token.isspace():
            if current and not current.endswith(" "):
                current += " "
                width += 1
            continue
        token_width = sum(_unit_width(char) for char in token)
        if current and width + token_width > max_width:
            lines.append(current.rstrip())
            current = token
            width = token_width
        else:
            current += token
            width += token_width
    if current.strip():
        lines.append(current.rstrip())
    if len(lines) > SUBTITLE_MAX_LINES:
        midpoint = max(1, (len(lines) + 1) // 2)
        lines = [" ".join(lines[:midpoint]), " ".join(lines[midpoint:])]
    return r"\N".join(lines)


def _write_ass(path: Path, text: str, duration: float, language: str, size: str) -> None:
    style = _select_subtitle(language, size)
    safe_text = _wrap_text(text, int(style["max_width"])).replace("{", "（").replace("}", "）")
    header = f"""[Script Info]
ScriptType: v4.00+
PlayResX: {style['canvas_width']}
PlayResY: {style['canvas_height']}
WrapStyle: 0
ScaledBorderAndShadow: yes

[V4+ Styles]
Format: Name, Fontname, Fontsize, PrimaryColour, SecondaryColour, OutlineColour, BackColour, Bold, Italic, Underline, StrikeOut, ScaleX, ScaleY, Spacing, Angle, BorderStyle, Outline, Shadow, Alignment, MarginL, MarginR, MarginV, Encoding
Style: Default,{style['font']},{style['font_size']},&H00FFFFFF,&H00FFFFFF,&H00101010,&H00000000,1,0,0,0,100,100,0,0,1,{style['outline']},{style['shadow']},{style['alignment']},{style['margin_left']},{style['margin_right']},{style['margin_vertical']},1

[Events]
Format: Layer, Start, End, Style, Name, MarginL, MarginR, MarginV, Effect, Text
Dialogue: 0,0:00:00.00,{_ass_time(duration)},Default,,0,0,0,,{safe_text}
"""
    path.write_text(header, encoding="utf-8")


def _filter_path(path: Path) -> str:
    return str(path.resolve()).replace("\\", "/").replace(":", r"\:").replace("'", r"\'")


def _static_filter(width: int, height: int) -> str:
    return (
        f"scale={width}:{height}:force_original_aspect_ratio=increase:flags=lanczos,"
        f"crop={width}:{height},setsar=1"
    )


def _motion_filter(
    motion: dict,
    duration: float,
    width: int,
    height: int,
    *,
    single_image: bool = False,
    start_delay: float = 0.0,
) -> str:
    values = {
        "zoom_from": float(motion.get("zoom_from", 1.0)),
        "zoom_to": float(motion.get("zoom_to", motion.get("zoom_from", 1.0))),
        "pan_from_x": float(motion.get("pan_from_x", 0.5)),
        "pan_from_y": float(motion.get("pan_from_y", 0.5)),
        "pan_to_x": float(motion.get("pan_to_x", motion.get("pan_from_x", 0.5))),
        "pan_to_y": float(motion.get("pan_to_y", motion.get("pan_from_y", 0.5))),
    }
    if not 1.0 <= values["zoom_from"] <= 2.0 or not 1.0 <= values["zoom_to"] <= 2.0:
        raise InvalidParameterError("motion", "zoom_from 和 zoom_to 必须在 1.0～2.0 之间")
    for key in ("pan_from_x", "pan_from_y", "pan_to_x", "pan_to_y"):
        if not 0.0 <= values[key] <= 1.0:
            raise InvalidParameterError("motion", f"{key} 必须在 0.0～1.0 之间")
    frames = max(1, round(duration * VIDEO_FPS))
    try:
        delay_seconds = float(start_delay)
    except (TypeError, ValueError) as exc:
        raise InvalidParameterError("start_delay", "start_delay 必须是非负数字") from exc
    if delay_seconds < 0:
        raise InvalidParameterError("start_delay", "start_delay 不能小于 0")
    delay_frames = min(frames - 1, round(delay_seconds * VIDEO_FPS))
    motion_frames = max(1, frames - delay_frames - 1)
    progress = (
        "1" if frames == 1 else
        (
            f"if(lt(on\\,{delay_frames})\\,0\\,(on-{delay_frames})/{motion_frames})"
            if delay_frames else f"on/{frames - 1}"
        )
    )
    smooth = f"({progress})*({progress})*(3-2*({progress}))"
    zoom = f"{values['zoom_from']}+({values['zoom_to']}-{values['zoom_from']})*({smooth})"
    pan_x = f"{values['pan_from_x']}+({values['pan_to_x']}-{values['pan_from_x']})*({smooth})"
    pan_y = f"{values['pan_from_y']}+({values['pan_to_y']}-{values['pan_from_y']})*({smooth})"
    camera_input_width = width * VIDEO_MOTION_SUPERSAMPLE
    camera_input_height = height * VIDEO_MOTION_SUPERSAMPLE
    frames_per_input = frames if single_image else 1
    return ",".join([
        f"scale={camera_input_width}:{camera_input_height}:force_original_aspect_ratio=increase:flags=bicubic,setsar=1",
        f"zoompan=z='{zoom}':x='(iw-iw/zoom)*({pan_x})':y='(ih-ih/zoom)*({pan_y})':"
        f"d={frames_per_input}:s={width}x{height}:fps={VIDEO_FPS},setsar=1",
    ])


def _render_shot(
    image_path: str | Path,
    output_path: str | Path,
    *,
    size: str,
    duration: float | None = None,
    audio_path: str | Path | None = None,
    audio_start: float | None = None,
    audio_end: float | None = None,
    subtitle: str | None = None,
    subtitle_language: str = "zh",
    motion: dict | None = None,
) -> dict:
    """合成单个镜头；有语音时始终以语音真实时长为准。"""
    width, height = _parse_size(size)
    image = _validate_file(image_path, "image_path")
    output = Path(output_path).resolve()
    if output.suffix.lower() != ".mp4":
        raise InvalidParameterError("output_path", "单镜头输出必须使用 .mp4 扩展名")

    audio = _validate_file(audio_path, "audio_path") if audio_path else None
    if audio:
        audio_duration = _probe(audio)["duration"]
        try:
            effective_audio_start = float(audio_start or 0)
            effective_audio_end = float(audio_end) if audio_end is not None else audio_duration
        except (TypeError, ValueError) as exc:
            raise InvalidParameterError("audio_start/audio_end", "音频起止时间必须是数字") from exc
        if effective_audio_start < 0 or effective_audio_end <= effective_audio_start:
            raise InvalidParameterError("audio_start/audio_end", "必须满足 0 ≤ audio_start < audio_end")
        if effective_audio_end > audio_duration + 0.01:
            raise InvalidParameterError(
                "audio_end",
                f"audio_end={effective_audio_end:.6f} 超过音频真实时长 {audio_duration:.6f}",
            )
        effective_audio_end = min(effective_audio_end, audio_duration)
        effective_duration = effective_audio_end - effective_audio_start
        duration_source = "audio"
    else:
        if audio_start is not None or audio_end is not None:
            raise InvalidParameterError("audio_start/audio_end", "只有传入 audio_path 时才能指定音频起止时间")
        effective_audio_start = None
        effective_audio_end = None
        try:
            effective_duration = float(duration or 0)
        except (TypeError, ValueError) as exc:
            raise InvalidParameterError("duration", "duration 必须是正数") from exc
        if effective_duration <= 0:
            raise InvalidParameterError("duration", "没有语音时必须传入大于 0 的 duration")
        duration_source = "duration"

    ffmpeg = _executable("ffmpeg")
    output.parent.mkdir(parents=True, exist_ok=True)
    with tempfile.TemporaryDirectory(prefix="video-shot-") as temporary:
        temporary_dir = Path(temporary)
        filters = (
            _motion_filter(motion, effective_duration, width, height, single_image=True)
            if motion else _static_filter(width, height)
        )
        if subtitle is not None and str(subtitle).strip():
            subtitle_file = temporary_dir / "subtitle.ass"
            _write_ass(subtitle_file, str(subtitle), effective_duration, subtitle_language, size)
            subtitle_filter = f"subtitles='{_filter_path(subtitle_file)}'"
            font_directory = next(
                (Path(value) for value in SUBTITLE_FONT_DIRECTORIES if Path(value).is_dir()),
                None,
            )
            if font_directory:
                subtitle_filter += f":fontsdir='{_filter_path(font_directory)}'"
            filters += f",{subtitle_filter}"

        command = [ffmpeg, "-y"]
        if motion:
            command.extend(["-framerate", str(VIDEO_FPS), "-i", str(image)])
        else:
            command.extend(["-loop", "1", "-framerate", str(VIDEO_FPS), "-i", str(image)])
        if audio:
            command.extend([
                "-ss", f"{effective_audio_start:.6f}",
                "-t", f"{effective_duration:.6f}",
                "-i", str(audio),
            ])
        else:
            command.extend([
                "-f", "lavfi", "-t", f"{effective_duration:.6f}",
                "-i", f"anullsrc=r={VIDEO_AUDIO_RATE}:cl=stereo",
            ])
        command.extend([
            "-vf", filters,
            "-map", "0:v:0", "-map", "1:a:0",
            "-t", f"{effective_duration:.6f}",
            "-r", str(VIDEO_FPS),
            "-c:v", VIDEO_CODEC, "-preset", VIDEO_PRESET, "-crf", str(VIDEO_CRF),
            "-pix_fmt", VIDEO_PIXEL_FORMAT,
            "-c:a", VIDEO_AUDIO_CODEC, "-ar", str(VIDEO_AUDIO_RATE), "-ac", str(VIDEO_AUDIO_CHANNELS),
            "-movflags", "+faststart",
            str(output),
        ])
        render_timeout = max(
            VIDEO_RENDER_MIN_TIMEOUT_SECONDS,
            effective_duration * VIDEO_RENDER_TIMEOUT_PER_SECOND,
        )
        _run(command, "单镜头渲染", timeout_seconds=render_timeout)

    result_probe = _probe(output)
    return {
        "output_path": str(output),
        "duration": round(effective_duration, 6),
        "actual_duration": round(result_probe["duration"], 6),
        "duration_source": duration_source,
        "has_audio": audio is not None,
        "has_subtitle": bool(subtitle is not None and str(subtitle).strip()),
        "has_motion": bool(motion),
        "audio_start": round(effective_audio_start, 6) if effective_audio_start is not None else None,
        "audio_end": round(effective_audio_end, 6) if effective_audio_end is not None else None,
    }
