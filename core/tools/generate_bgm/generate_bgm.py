"""按目标时长循环或裁剪源曲，产出固定音量的 BGM 音轨。"""

from __future__ import annotations

import json
import os
import shutil
import subprocess
from pathlib import Path
from uuid import uuid4

from ._constants import (
    BGM_AUDIO_CHANNELS,
    BGM_AUDIO_CODEC,
    BGM_AUDIO_RATE,
    BGM_FADE_IN_SECONDS,
    BGM_FADE_OUT_SECONDS,
    BGM_GAIN,
    BGM_GENERATE_MIN_TIMEOUT_SECONDS,
    BGM_GENERATE_TIMEOUT_PER_SECOND,
    BGM_PROBE_TIMEOUT_SECONDS,
)
from ._errors import (
    BGMFileNotFoundError,
    FFmpegNotFoundError,
    InvalidParameterError,
    MediaProbeError,
    RenderError,
    RenderTimeoutError,
)

__all__ = ["generate_bgm"]


def _executable(name: str) -> str:
    resolved = shutil.which(name)
    if not resolved:
        raise FFmpegNotFoundError(name)
    return resolved


def _validate_file(value: str | Path, parameter: str) -> Path:
    path = Path(value).resolve()
    if not path.is_file():
        raise BGMFileNotFoundError(parameter, str(path))
    return path


def _probe(path: Path) -> dict:
    ffprobe = _executable("ffprobe")
    try:
        completed = subprocess.run(
            [
                ffprobe,
                "-v", "error",
                "-show_entries", "format=duration",
                "-of", "json",
                str(path),
            ],
            check=False,
            capture_output=True,
            text=True,
            encoding="utf-8",
            errors="replace",
            timeout=BGM_PROBE_TIMEOUT_SECONDS,
        )
    except subprocess.TimeoutExpired as extra:
        raise MediaProbeError(f"读取媒体信息超过 {BGM_PROBE_TIMEOUT_SECONDS} 秒：{path}") from extra
    try:
        payload = json.loads(completed.stdout or "{}")
        duration = float((payload.get("format") or {}).get("duration") or 0)
    except (TypeError, ValueError, json.JSONDecodeError) as extra:
        raise MediaProbeError(f"无法读取媒体信息：{path}") from extra
    if completed.returncode != 0 or duration <= 0:
        detail = (completed.stderr or "").strip()[-1200:]
        raise MediaProbeError(f"无法读取媒体时长：{path}。{detail}")
    return {"duration": duration}


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
    except subprocess.TimeoutExpired as extra:
        raise RenderTimeoutError(timeout_seconds) from extra
    if completed.returncode != 0:
        detail = (completed.stderr or completed.stdout or "").strip()[-3000:]
        raise RenderError(f"生成 BGM 失败：{detail or '未知 FFmpeg 错误'}")


def _fade_seconds(value: float | None, default: float, duration: float, parameter: str) -> float:
    if value is None:
        chosen = default
    else:
        try:
            chosen = float(value)
        except (TypeError, ValueError) as extra:
            raise InvalidParameterError(parameter, f"{parameter} 必须是数字") from extra
    if chosen < 0:
        raise InvalidParameterError(parameter, f"{parameter} 不能小于 0")
    return max(0.0, min(chosen, duration))


def generate_bgm(
    bgm_path: str | Path,
    output_path: str | Path,
    duration: float,
    *,
    fade_in: float | None = None,
    fade_out: float | None = None,
) -> dict:
    """产出一条对齐目标时长的 BGM。短则循环，长则裁剪；音量固定。不混入视频。"""
    source = _validate_file(bgm_path, "bgm_path")
    try:
        target_duration = float(duration)
    except (TypeError, ValueError) as extra:
        raise InvalidParameterError("duration", "duration 必须是数字") from extra
    if target_duration <= 0:
        raise InvalidParameterError("duration", "duration 必须大于 0")
    destination = Path(output_path).resolve()
    if destination.suffix.lower() != ".m4a":
        raise InvalidParameterError("output_path", "输出必须使用 .m4a 扩展名")
    destination.parent.mkdir(parents=True, exist_ok=True)

    source_duration = _probe(source)["duration"]
    looped = source_duration + 0.01 < target_duration
    fade_in_value = _fade_seconds(fade_in, BGM_FADE_IN_SECONDS, target_duration, "fade_in")
    fade_out_value = _fade_seconds(fade_out, BGM_FADE_OUT_SECONDS, target_duration, "fade_out")
    fade_out_start = max(0.0, target_duration - fade_out_value)

    filters = [
        f"atrim=0:{target_duration:.9f}",
        "asetpts=PTS-STARTPTS",
        f"aresample={BGM_AUDIO_RATE}",
        "aformat=channel_layouts=stereo",
        f"volume={BGM_GAIN:.6f}",
    ]
    if fade_in_value > 0:
        filters.append(f"afade=t=in:st=0:d={fade_in_value:.6f}")
    if fade_out_value > 0:
        filters.append(f"afade=t=out:st={fade_out_start:.6f}:d={fade_out_value:.6f}")

    ffmpeg = _executable("ffmpeg")
    command = [ffmpeg, "-y"]
    if looped:
        command.extend(["-stream_loop", "-1"])
    command.extend([
        "-i", str(source),
        "-t", f"{target_duration:.9f}",
        "-af", ",".join(filters),
        "-c:a", BGM_AUDIO_CODEC, "-ar", str(BGM_AUDIO_RATE), "-ac", str(BGM_AUDIO_CHANNELS),
        "-movflags", "+faststart",
    ])
    timeout_seconds = max(BGM_GENERATE_MIN_TIMEOUT_SECONDS, target_duration * BGM_GENERATE_TIMEOUT_PER_SECOND)
    temporary = destination.with_name(f".{destination.stem}-{uuid4().hex}.tmp.m4a")
    try:
        _run([*command, str(temporary)], timeout_seconds)
        _probe(temporary)
        os.replace(temporary, destination)
    finally:
        if temporary.exists():
            temporary.unlink(missing_ok=True)

    return {
        "output_path": str(destination),
        "duration": round(_probe(destination)["duration"], 6),
        "bgm_path": str(source),
        "gain": BGM_GAIN,
        "looped": looped,
        "fade_in": fade_in_value,
        "fade_out": fade_out_value,
    }
