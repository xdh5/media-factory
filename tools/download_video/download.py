"""从分享口令或链接解析并下载视频到本地。"""

from __future__ import annotations

import os
import re
import shutil
import subprocess
import time
from pathlib import Path
from uuid import uuid4

import requests
from requests.adapters import HTTPAdapter
from requests.exceptions import ChunkedEncodingError, ConnectionError, RequestException, Timeout
from urllib3.util.retry import Retry

from ._constants import DOWNLOAD_CONNECT_TIMEOUT_SECONDS, DOWNLOAD_TIMEOUT_SECONDS, MUX_TIMEOUT_SECONDS
from ._errors import DownloadError, FFmpegNotFoundError, InvalidParameterError, ParseLinkError
from ._extractor import parse_share_text

__all__ = ["download"]

_HEADERS_TIMEOUT = (DOWNLOAD_CONNECT_TIMEOUT_SECONDS, DOWNLOAD_TIMEOUT_SECONDS)
# 读流中断（IncompleteRead 等）发生在响应已开始之后，urllib3 Retry 不会重试，需要整段重下。
_STREAM_ATTEMPTS = 5


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
    """带防盗链请求头流式下载。连接中断时整段重试，最终失败时清理半成品文件。"""
    session = requests.Session()
    retry = Retry(
        total=5,
        backoff_factor=1,
        status_forcelist=[500, 502, 503, 504],
        allowed_methods=["GET"],
    )
    session.mount("http://", HTTPAdapter(max_retries=retry))
    session.mount("https://", HTTPAdapter(max_retries=retry))
    last_error: RequestException | None = None
    for attempt in range(1, _STREAM_ATTEMPTS + 1):
        try:
            with session.get(url, headers=headers, stream=True, timeout=_HEADERS_TIMEOUT) as response:
                response.raise_for_status()
                with destination.open("wb") as target:
                    for chunk in response.iter_content(chunk_size=512 * 1024):
                        if chunk:
                            target.write(chunk)
            last_error = None
            break
        except (ChunkedEncodingError, ConnectionError, Timeout) as extra:
            destination.unlink(missing_ok=True)
            last_error = extra
            if attempt >= _STREAM_ATTEMPTS:
                break
            time.sleep(attempt)
        except RequestException as extra:
            destination.unlink(missing_ok=True)
            raise DownloadError(f"下载失败：{extra}", {"url": url}) from extra
    if last_error is not None:
        raise DownloadError(
            f"下载失败（已重试 {_STREAM_ATTEMPTS} 次）：{last_error}",
            {"url": url},
        ) from last_error
    if not destination.is_file() or destination.stat().st_size <= 0:
        destination.unlink(missing_ok=True)
        raise DownloadError("下载完成但文件为空，请换一条链接后重试", {"url": url})


def _stream_from_candidates(urls: list[str], destination: Path, headers: dict[str, str]) -> None:
    """依次尝试解析结果中的 CDN 地址，全部失败后再报告最后一个错误。"""
    candidates = list(dict.fromkeys(item for item in urls if item.startswith("http")))
    last_error: DownloadError | None = None
    for url in candidates:
        try:
            _stream_to_file(url, destination, headers)
            return
        except DownloadError as extra:
            last_error = extra
    if last_error is None:
        raise DownloadError("解析成功但没有可用的视频下载地址")
    raise DownloadError(
        f"全部 {len(candidates)} 个视频地址均下载失败，最后一次错误：{last_error}",
        {"candidate_count": len(candidates), **last_error.details},
    ) from last_error


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
    video_urls = resolved.video_urls or [resolved.video_url]
    try:
        if audio_url:
            video_part = temporary.with_suffix(".video")
            audio_part = temporary.with_suffix(".audio")
            try:
                _stream_from_candidates(video_urls, video_part, resolved.headers)
                _stream_to_file(audio_url, audio_part, resolved.headers)
                _mux(video_part, audio_part, temporary)
            finally:
                video_part.unlink(missing_ok=True)
                audio_part.unlink(missing_ok=True)
        else:
            _stream_from_candidates(video_urls, temporary, resolved.headers)
        os.replace(temporary, destination)
    finally:
        temporary.unlink(missing_ok=True)
    return {
        "video_id": resolved.video_id,
        "platform": resolved.platform_name,
        "title": resolved.title or None,
        "description": resolved.description or "",
        "topics": list(resolved.topics),
        "video_path": str(destination),
        "cover_url": resolved.cover_url or None,
    }
