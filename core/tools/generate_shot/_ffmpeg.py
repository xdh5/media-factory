"""generate_shot 包内部的 FFmpeg 探测、校验与编码参数。"""

from __future__ import annotations

import json
import shutil
import subprocess
from pathlib import Path

from ._constants import (
    SHOT_CODEC,
    SHOT_CRF,
    SHOT_PIXEL_FORMAT,
    SHOT_PRESET,
    SHOT_PROBE_TIMEOUT_SECONDS,
    SHOT_TUNE_STILLIMAGE,
)
from ._errors import (
    FFmpegNotFoundError,
    MediaFileNotFoundError,
    MediaProbeError,
    RenderError,
    RenderTimeoutError,
)


def _executable(name: str) -> str:
    executable = shutil.which(name)
    if not executable:
        raise FFmpegNotFoundError(name)
    return executable


def _run(command: list[str], context: str, *, timeout_seconds: float) -> None:
    argv = list(command)
    if argv and "-nostdin" not in argv:
        argv.insert(1, "-nostdin")
    try:
        completed = subprocess.run(
            argv,
            check=False,
            capture_output=True,
            text=True,
            encoding="utf-8",
            errors="replace",
            timeout=timeout_seconds,
        )
    except subprocess.TimeoutExpired as extra:
        raise RenderTimeoutError(context, timeout_seconds) from extra
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
            timeout=SHOT_PROBE_TIMEOUT_SECONDS,
        )
    except subprocess.TimeoutExpired as extra:
        raise MediaProbeError(
            f"读取媒体信息超过 {SHOT_PROBE_TIMEOUT_SECONDS} 秒：{path}"
        ) from extra
    try:
        payload = json.loads(completed.stdout or "{}")
        duration = float((payload.get("format") or {}).get("duration") or 0)
    except (TypeError, ValueError, json.JSONDecodeError) as extra:
        raise MediaProbeError(f"无法读取媒体信息：{path}") from extra
    if completed.returncode != 0 or duration <= 0:
        detail = (completed.stderr or "").strip()[-1200:]
        raise MediaProbeError(f"无法读取媒体时长：{path}。{detail}")
    return {"duration": duration, "streams": payload.get("streams") or []}


def _validate_file(value: str | Path, parameter: str) -> Path:
    path = Path(value).resolve()
    if not path.is_file():
        raise MediaFileNotFoundError(parameter, str(path))
    return path


def _encode_video_args(*, still_image: bool) -> list[str]:
    args = [
        "-c:v", SHOT_CODEC, "-preset", SHOT_PRESET, "-crf", str(SHOT_CRF),
        "-pix_fmt", SHOT_PIXEL_FORMAT,
    ]
    if still_image:
        args.extend(["-tune", SHOT_TUNE_STILLIMAGE])
    return args
