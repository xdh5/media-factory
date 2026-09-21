"""从分享口令或链接解析并下载视频到本地。"""

from __future__ import annotations

import os
import re
import shutil
import subprocess
from pathlib import Path
from uuid import uuid4

import requests
from requests.adapters import HTTPAdapter
from requests.exceptions import RequestException
from urllib3.util.retry import Retry

from ._constants import DOWNLOAD_CONNECT_TIMEOUT_SECONDS, DOWNLOAD_TIMEOUT_SECONDS, MUX_TIMEOUT_SECONDS
from ._errors import DownloadError, FFmpegNotFoundError, InvalidParameterError, ParseLinkError
from ._extractor import parse_share_text

__all__ = ["download"]

_HEADERS_TIMEOUT = (DOWNLOAD_CONNECT_TIMEOUT_SECONDS, DOWNLOAD_TIMEOUT_SECONDS)


def _safe_filename(video_id: str) -> str:
    safe_id = re.sub(r"[^A-Za-z0-9_.-]", "_", video_id or "").strip("._")
    return f"{safe_id or 'video'}.mp4"


def _destination(output_path: str | Path | None, video_id: str) -> Path:
    if output_path is None:
        from ._constants import DEFAULT_VIDEO_DIR

        DEFAULT_VIDEO_DIR.mkdir(parents=True, exist_ok=True)
        return (DEFAULT_VIDEO_DIR / _safe_filename(video_id)).resolve()
    destination = Path(output_path).resolve()
    if destination.suffix.lower() != ".mp4":
        raise InvalidParameterError("output_path", "输出必须使用 .mp4 扩展名")
    destination.parent.mkdir(parents=True, exist_ok=True)
    return destination


def _stream_to_file(url: str, destination: Path, headers: dict[str, str]) -> None:
    """带防盗链请求头流式下载，失败时清理半成品文件。"""
    session = requests.Session()
    retry = Retry(
        total=5,
        backoff_factor=1,
        status_forcelist=[500, 502, 503, 504],
        allowed_methods=["GET"],
    )
    session.mount("http://", HTTPAdapter(max_retries=retry))
    session.mount("https://", HTTPAdapter(max_retries=retry))
    try:
        with session.get(url, headers=headers, stream=True, timeout=_HEADERS_TIMEOUT) as response:
            response.raise_for_status()
            with destination.open("wb") as target:
                for chunk in response.iter_content(chunk_size=512 * 1024):
                    if chunk:
                        target.write(chunk)
    except RequestException as extra:
        destination.unlink(missing_ok=True)
        raise DownloadError(f"下载失败：{extra}", {"url": url}) from extra
    if not destination.is_file() or destination.stat().st_size <= 0:
        destination.unlink(missing_ok=True)
        raise DownloadError("下载完成但文件为空，请换一条链接后重试", {"url": url})


def _mux(video_file: Path, audio_file: Path, destination: Path) -> None:
    ffmpeg = shutil.which("ffmpeg")
    if not ffmpeg:
        raise FFmpegNotFoundError()
    command = [
        ffmpeg, "-y",
        "-i", str(video_file),
        "-i", str(audio_file),
        "-c", "copy",
        "-movflags", "+faststart",
        str(destination),
    ]
    try:
        completed = subprocess.run(
            command,
            check=False,
            capture_output=True,
            text=True,
            encoding="utf-8",
            errors="replace",
            timeout=MUX_TIMEOUT_SECONDS,
        )
    except subprocess.TimeoutExpired as extra:
        raise DownloadError(f"音视频合并超过 {MUX_TIMEOUT_SECONDS} 秒") from extra
    if completed.returncode != 0 or not destination.is_file() or destination.stat().st_size <= 0:
        detail = (completed.stderr or completed.stdout or "").strip()[-1500:]
        destination.unlink(missing_ok=True)
        raise DownloadError(f"音视频合并失败：{detail or 'ffmpeg 没有写出文件'}")


def download(share_text: str, output_path: str | Path | None = None) -> dict:
    """解析分享文字或链接，把视频下载到本地，返回 video_path。"""
    text = str(share_text or "").strip()
    if not text:
        raise InvalidParameterError("share_text", "share_text 不能为空，请粘贴平台分享口令或视频链接")
    resolved = parse_share_text(text)
    if not resolved.video_url:
        raise ParseLinkError("解析成功但没有视频地址，请换一条链接后重试", {"share_text": text})
    destination = _destination(output_path, resolved.video_id)

    # 分轨（视频+独立音轨）时分别下载后用 ffmpeg 合并。
    audio_url = resolved.audio_url.strip()
    temporary = destination.with_name(f".{destination.stem}-{uuid4().hex}.tmp.mp4")
    try:
        if audio_url:
            video_part = temporary.with_suffix(".video")
            audio_part = temporary.with_suffix(".audio")
            try:
                _stream_to_file(resolved.video_url, video_part, resolved.headers)
                _stream_to_file(audio_url, audio_part, resolved.headers)
                _mux(video_part, audio_part, temporary)
            finally:
                video_part.unlink(missing_ok=True)
                audio_part.unlink(missing_ok=True)
        else:
            _stream_to_file(resolved.video_url, temporary, resolved.headers)
        os.replace(temporary, destination)
    finally:
        temporary.unlink(missing_ok=True)
    return {
        "video_id": resolved.video_id,
        "platform": resolved.platform_name,
        "title": resolved.title or None,
        "video_path": str(destination),
        "cover_url": resolved.cover_url or None,
    }
