"""只读取远程短片段，供宿主取证和准备发布素材。"""

from __future__ import annotations

import subprocess
from pathlib import Path

from download_video._extractor import parse_share_text

from .._errors import AnimeError
from .compile import _executable, _probe, _subprocess_kwargs


def extract_remote_preview(work: dict, destination: Path, start: float = 0, seconds: float = 60) -> dict:
    """由解析器取得临时流地址，远程定位并截取，不回退为整集下载。"""
    if destination.is_file():
        return _probe(destination)
    resolved = parse_share_text(work["work_url"])
    if str(resolved.video_id) != str(work["aweme_id"]):
        raise AnimeError("预览来源 ID 与选定作品不一致")
    destination.parent.mkdir(parents=True, exist_ok=True)
    temporary = destination.with_name(destination.stem + ".partial.mp4")
    headers = "".join(f"{key}: {value}\r\n" for key, value in resolved.headers.items())
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
