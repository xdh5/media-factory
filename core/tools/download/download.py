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

from ._constants import (
    DEFAULT_REFERER,
    DEFAULT_VIDEO_DIR,
    DOWNLOAD_CONNECT_TIMEOUT_SECONDS,
    DOWNLOAD_TIMEOUT_SECONDS,
    MUX_TIMEOUT_SECONDS,
    PLATFORM_REFERER,
)
from ._errors import DownloadError, FFmpegNotFoundError, InvalidParameterError, ParseLinkError
from ._parser.service import ParserError, ParserService

__all__ = ["download"]

_PARSE_HINTS = {
    "No valid video URL found": "分享内容里没有有效视频链接。请传入含 http/https 的抖音、快手、小红书、B 站等分享口令或链接",
    "Unsupported video URL": "不支持该平台链接。请确认是抖音、快手、小红书、哔哩哔哩、好看视频、微视、梨视频或皮皮搞笑",
}


def _safe_filename(video_id: str) -> str:
    safe_id = re.sub(r"[^A-Za-z0-9_.-]", "_", video_id or "").strip("._")
    return f"{safe_id or 'video'}.mp4"


def _parse(share_text: str) -> dict:
    text = str(share_text or "").strip()
    if not text:
        raise InvalidParameterError("share_text", "share_text 不能为空，请粘贴平台分享口令或视频链接")
    try:
        parsed = ParserService().parse(text)
    except ParserError as extra:
        hint = _PARSE_HINTS.get(str(extra))
        if hint:
            raise ParseLinkError(hint, {"share_text": text}) from extra
        if "Parse failed" in str(extra) or "DOUYIN_COOKIE" in str(extra):
            raise ParseLinkError(
                "解析失败：拿不到平台视频地址。抖音请在 .env 填写有效 DOUYIN_COOKIE 后重试",
                {"share_text": text},
            ) from extra
        raise ParseLinkError(f"解析失败：{extra}", {"share_text": text}) from extra
    except Exception as extra:
        raise ParseLinkError(f"解析失败：{type(extra).__name__}: {extra}", {"share_text": text}) from extra
    if not parsed.get("video_url"):
        raise ParseLinkError("解析成功但没有 video_url，请换一条链接或检查该平台是否可匿名解析")
    return parsed


def _destination(output_path: str | Path | None, video_id: str) -> Path:
    if output_path is None:
        DEFAULT_VIDEO_DIR.mkdir(parents=True, exist_ok=True)
        return (DEFAULT_VIDEO_DIR / _safe_filename(video_id)).resolve()
    destination = Path(output_path).resolve()
    if destination.suffix.lower() != ".mp4":
        raise InvalidParameterError("output_path", "输出必须使用 .mp4 扩展名")
    destination.parent.mkdir(parents=True, exist_ok=True)
    return destination


def _headers(platform: str) -> dict[str, str]:
    return {
        "User-Agent": (
            "Mozilla/5.0 (Windows NT 10.0; Win64; x64) AppleWebKit/537.36 "
            "Chrome/123.0 Safari/537.36"
        ),
        "Referer": PLATFORM_REFERER.get(platform, DEFAULT_REFERER),
    }


def _download_url(url: str, destination: Path, platform: str) -> None:
    session = requests.Session()
    retry = Retry(
        total=5,
        backoff_factor=1,
        status_forcelist=[500, 502, 503, 504],
        allowed_methods=["GET"],
    )
    session.mount("http://", HTTPAdapter(max_retries=retry))
    session.mount("https://", HTTPAdapter(max_retries=retry))
    timeout = (DOWNLOAD_CONNECT_TIMEOUT_SECONDS, DOWNLOAD_TIMEOUT_SECONDS)
    try:
        with session.get(url, headers=_headers(platform), stream=True, timeout=timeout) as response:
            response.raise_for_status()
            with destination.open("wb") as target:
                for chunk in response.iter_content(chunk_size=512 * 1024):
                    if chunk:
                        target.write(chunk)
    except RequestException as extra:
        destination.unlink(missing_ok=True)
        raise DownloadError(f"下载失败：{extra}", {"url": url, "platform": platform}) from extra
    if not destination.is_file() or destination.stat().st_size <= 0:
        destination.unlink(missing_ok=True)
        raise DownloadError("下载完成但文件为空，请换一条链接后重试", {"url": url, "platform": platform})


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
    parsed = _parse(share_text)
    destination = _destination(output_path, str(parsed.get("video_id") or ""))
    platform = str(parsed.get("platform") or "")
    video_url = str(parsed["video_url"])
    audio_url = str(parsed.get("audio_url") or "").strip()
    temporary = destination.with_name(f".{destination.stem}-{uuid4().hex}.tmp.mp4")
    try:
        if audio_url:
            video_part = temporary.with_suffix(".video")
            audio_part = temporary.with_suffix(".audio")
            try:
                _download_url(video_url, video_part, platform)
                _download_url(audio_url, audio_part, platform)
                _mux(video_part, audio_part, temporary)
            finally:
                video_part.unlink(missing_ok=True)
                audio_part.unlink(missing_ok=True)
        else:
            _download_url(video_url, temporary, platform)
        os.replace(temporary, destination)
    finally:
        temporary.unlink(missing_ok=True)
    return {
        "video_id": parsed.get("video_id") or "",
        "platform": platform,
        "title": parsed.get("title"),
        "video_path": str(destination),
        "cover_url": parsed.get("cover_url"),
    }
