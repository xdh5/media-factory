"""只读取远程短片段和容器信息，供宿主取证和准备发布素材。"""

from __future__ import annotations

import json
import subprocess
from pathlib import Path

from download_video._extractor import parse_share_text

from .._errors import AnimeError
from .compile import _executable, _probe, _subprocess_kwargs


def _remote_headers(resolved) -> str:
    return "".join(f"{key}: {value}\r\n" for key, value in resolved.headers.items())


def probe_remote_duration(resolved) -> float:
    """只读远程流容器的时长，不下载整部长视频。"""
    command = [_executable("ffprobe"), "-v", "error", "-rw_timeout", "30000000",
               "-headers", _remote_headers(resolved), "-show_entries", "format=duration",
               "-of", "json", resolved.video_url]
    completed = subprocess.run(command, capture_output=True, text=True, encoding="utf-8",
                               errors="replace", timeout=180, **_subprocess_kwargs())
    if completed.returncode != 0:
        detail = (completed.stderr or "").strip()[-500:]
        raise AnimeError(f"读取远程视频时长失败：{detail or 'ffprobe 没有返回结果'}")
    duration = float((json.loads(completed.stdout or "{}").get("format") or {}).get("duration") or 0)
    if duration <= 0:
        raise AnimeError("远程视频时长无效，不能制定拆分计划")
    return duration


def extract_remote_preview(work: dict, destination: Path, start: float = 0, seconds: float = 60) -> dict:
    """由解析器取得临时流地址，远程定位并截取，不回退为整集下载。"""
    if destination.is_file():
        return _probe(destination)
    resolved = parse_share_text(work["work_url"])
    if str(resolved.video_id) != str(work["aweme_id"]):
        raise AnimeError("预览来源 ID 与选定作品不一致")
    destination.parent.mkdir(parents=True, exist_ok=True)
    temporary = destination.with_name(destination.stem + ".partial.mp4")
    headers = _remote_headers(resolved)
    command = [_executable("ffmpeg"), "-v", "error", "-y"]
    for url in [resolved.video_url] + ([resolved.audio_url] if resolved.audio_url else []):
        command.extend(["-rw_timeout", "30000000", "-headers", headers, "-ss", str(start), "-i", url])
    command.extend(["-t", str(seconds), "-map", "0:v:0", "-map", "1:a:0" if resolved.audio_url else "0:a:0?",
                    "-vf", "scale=1280:720:force_original_aspect_ratio=decrease",
                    "-c:v", "libx264", "-preset", "veryfast", "-crf", "23", "-c:a", "aac", str(temporary)])
    try:
        result = subprocess.run(command, capture_output=True, timeout=180, **_subprocess_kwargs())
        if result.returncode:
            raise AnimeError("远程片段截取失败；未回退为整集下载，请检查来源或网络")
        probe = _probe(temporary)
        if probe["duration"] > seconds + 2:
            raise AnimeError("远程片段长度超过预期")
        temporary.replace(destination)
        return probe
    except subprocess.TimeoutExpired:
        raise AnimeError("远程片段读取超时；未回退为整集下载") from None
    finally:
        temporary.unlink(missing_ok=True)
