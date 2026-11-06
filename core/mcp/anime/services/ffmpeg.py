"""动漫视频探测、命令执行和编码进度。"""

from __future__ import annotations

import json
import re
import shutil
import subprocess
import sys
import threading
import time
from pathlib import Path
from typing import Callable


from .._errors import AnimeError


Progress = Callable[[str], None]

_TIME_RE = re.compile(r"(\d+):(\d+):(\d+(?:\.\d+)?)")

def run_ffmpeg(
    command: list[str],
    *,
    total_seconds: float,
    progress: Progress | None,
    label: str,
) -> None:
    log_path = Path(command[-1]).with_suffix(".ffmpeg.log")
    timeout = max(600.0, total_seconds * 8 + 120.0)
    kwargs = subprocess_options()
    with log_path.open("w", encoding="utf-8", errors="replace") as log_file:
        process = subprocess.Popen(
            command,
            stdout=subprocess.PIPE,
            stderr=log_file,
            text=True,
            encoding="utf-8",
            errors="replace",
            **kwargs,
        )
        last_report = 0.0

        def _read_progress() -> None:
            nonlocal last_report
            assert process.stdout is not None
            for line in process.stdout:
                timestamp = _parse_progress_time(line)
                if timestamp is None or progress is None or total_seconds <= 0:
                    continue
                now = time.monotonic()
                if now - last_report < 5:
                    continue
                last_report = now
                percent = min(99, max(0, int(timestamp / total_seconds * 100)))
                report_progress(progress, f"正在编码{label}（约 {percent}%）")

        reader = threading.Thread(target=_read_progress, daemon=True)
        reader.start()
        try:
            return_code = process.wait(timeout=timeout)
        except subprocess.TimeoutExpired as exc:
            process.kill()
            process.wait(timeout=30)
            raise AnimeError(f"{label} 编码超过 {int(timeout)} 秒") from exc
        reader.join(timeout=5)
    if return_code != 0:
        detail = ""
        if log_path.is_file():
            detail = log_path.read_text(encoding="utf-8", errors="replace").strip()[-1500:]
        raise AnimeError(f"{label} 拼接失败：{detail or 'ffmpeg 没有写出文件'}")
    log_path.unlink(missing_ok=True)


def _parse_progress_time(line: str) -> float | None:
    text = line.strip()
    if text.startswith("out_time_us="):
        try:
            return int(text.split("=", 1)[1]) / 1_000_000
        except ValueError:
            return None
    if text.startswith("out_time_ms=") and not text.startswith("out_time_ms=N/A"):
        # 新版 ffmpeg 的 out_time_ms 实际是微秒。
        try:
            return int(text.split("=", 1)[1]) / 1_000_000
        except ValueError:
            return None
    if text.startswith("out_time="):
        matched = _TIME_RE.search(text.split("=", 1)[1])
        if not matched:
            return None
        hours, minutes, seconds = matched.groups()
        return int(hours) * 3600 + int(minutes) * 60 + float(seconds)
    return None


def probe_video(path: Path) -> dict:
    ffprobe = media_executable("ffprobe")
    command = [
        ffprobe, "-v", "error",
        "-show_entries",
        "format=duration:stream=index,codec_type,codec_name,width,height,avg_frame_rate,pix_fmt,sample_rate,channels,disposition,extradata_hash",
        "-show_data_hash", "sha256",
        "-of", "json",
        str(path),
    ]
    try:
        completed = subprocess.run(
            command,
            check=False,
            capture_output=True,
            text=True,
            encoding="utf-8",
            errors="replace",
            timeout=60,
            **subprocess_options(),
        )
    except subprocess.TimeoutExpired as exc:
        raise AnimeError(f"读取视频信息超时：{path.name}") from exc
    try:
        payload = json.loads(completed.stdout or "{}")
    except json.JSONDecodeError as exc:
        raise AnimeError(f"无法读取视频信息：{path.name}") from exc
    duration = float((payload.get("format") or {}).get("duration") or 0)
    if completed.returncode != 0 or duration <= 0:
        detail = (completed.stderr or "").strip()[-800:]
        raise AnimeError(f"无法读取视频时长：{path.name}。{detail}")
    streams = payload.get("streams") or []
    videos = [
        stream for stream in streams
        if stream.get("codec_type") == "video"
        and not int((stream.get("disposition") or {}).get("attached_pic") or 0)
    ]
    audios = [stream for stream in streams if stream.get("codec_type") == "audio"]
    if not videos:
        raise AnimeError(f"文件里没有画面：{path.name}")
    video = videos[0]
    audio = audios[0] if audios else None
    width = int(video.get("width") or 0)
    height = int(video.get("height") or 0)
    return {
        "duration": duration,
        "width": width,
        "height": height,
        "vcodec": video.get("codec_name") or "",
        "pix_fmt": video.get("pix_fmt") or "",
        "fps_token": str(video.get("avg_frame_rate") or ""),
        "video_stream_index": int(video.get("index") or 0),
        "acodec": (audio or {}).get("codec_name") or "",
        "sample_rate": str((audio or {}).get("sample_rate") or ""),
        "channels": int((audio or {}).get("channels") or 0),
        "audio_extradata_hash": (audio or {}).get("extradata_hash") or "",
        "audio_stream_index": None if audio is None else int(audio.get("index") or 0),
    }


def media_executable(name: str) -> str:
    executable = shutil.which(name)
    if not executable:
        raise AnimeError(f"未找到 {name}，请确认已安装并加入 PATH")
    return executable


def subprocess_options() -> dict:
    if sys.platform == "win32":
        return {"creationflags": subprocess.CREATE_NO_WINDOW}
    return {}


def report_progress(progress: Progress | None, message: str) -> None:
    if progress is not None:
        progress(message)
