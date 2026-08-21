from __future__ import annotations

import os
import re
from pathlib import Path

import requests
from requests.adapters import HTTPAdapter
from requests.exceptions import ChunkedEncodingError, RequestException
from urllib3.util.retry import Retry

from ._log import logger

from .config import DOMAIN_TO_NAME, MINI_PROGRAM_LEGAL_DOMAIN, VIDEO_DIR
from .factory import DownloaderFactory
from .url import UrlParser, WebFetcher


class ParserError(RuntimeError):
    def __init__(self, message: str, status_code: int = 400):
        super().__init__(message)
        self.status_code = status_code


def _is_xiaohongshu(domain: str) -> bool:
    return "xiaohongshu.com" in domain or "xhslink.com" in domain


def _is_bilibili(domain: str) -> bool:
    return "bilibili.com" in domain or "b23.tv" in domain


def _safe_filename(video_id: str) -> str:
    safe_id = re.sub(r"[^A-Za-z0-9_.-]", "_", video_id or "").strip("._")
    return f"{safe_id or 'video'}.mp4"


def _clean_title(title: str) -> str:
    """清洗视频标题：去掉开头的「第X集 |」前缀和结尾的 #话题标签。"""
    if not title:
        return title
    title = re.sub(r"^第\d+集\s*[|｜]\s*", "", title)
    title = re.sub(r"(?:\s*#[^\s#]+)+\s*$", "", title)
    return title.strip()


class ParserService:
    """Platform parsing and server-side download without HTTP framework concerns."""

    def parse_and_download(self, text: str) -> dict:
        """Resolve share text and download its video in one reusable call."""
        parsed = self.parse(text)
        downloaded = self.download(parsed["video_url"], parsed["video_id"])
        return {**parsed, **downloaded}

    def parse(self, text: str) -> dict:
        extracted_url = UrlParser.get_url(text)
        if not extracted_url:
            raise ParserError("No valid video URL found")

        redirect_url = WebFetcher.fetch_redirect_url(extracted_url) or extracted_url
        domain = UrlParser.get_domain(redirect_url)
        platform = DOMAIN_TO_NAME.get(domain)
        if not platform:
            raise ParserError("Unsupported video URL")

        video_id = UrlParser.get_video_id(redirect_url)
        real_url = UrlParser.extract_video_address(redirect_url)
        attempts = 5 if _is_xiaohongshu(domain) else 1
        downloader = None
        title = cover_url = video_url = None

        for attempt in range(attempts):
            downloader = DownloaderFactory.create_downloader(platform, real_url)
            title = downloader.get_title_content()
            video_url = downloader.get_real_video_url()
            cover_url = downloader.get_cover_photo_url()
            if video_url:
                break
            logger.debug("Parse attempt %s/%s failed for %s", attempt + 1, attempts, platform)

        if not video_url:
            raise ParserError(
                "Parse failed: platform metadata unavailable. For Douyin, set a fresh DOUYIN_COOKIE and restart.",
                502,
            )

        result = {
            "video_id": video_id,
            "platform": platform,
            "title": _clean_title(title),
            "video_url": UrlParser.convert_to_https(video_url),
            "cover_url": UrlParser.convert_to_https(cover_url),
        }
        if _is_bilibili(domain) and downloader and hasattr(downloader, "get_audio_url"):
            audio_url = downloader.get_audio_url()
            if audio_url:
                result["audio_url"] = UrlParser.convert_to_https(audio_url)
        return result

    def download(self, video_url: str, video_id: str) -> dict:
        domain = UrlParser.get_domain(video_url)
        if domain in MINI_PROGRAM_LEGAL_DOMAIN:
            return {"download_url": video_url}

        filename = _safe_filename(video_id)
        output_path = Path(VIDEO_DIR) / filename
        if not output_path.exists():
            try:
                self._download_to(video_url, output_path)
            except (RequestException, ChunkedEncodingError, OSError) as exc:
                logger.warning("Server download failed; returning source URL: %s", exc)
                output_path.unlink(missing_ok=True)
                return {"download_url": video_url}

        return {"download_url": f"/static/videos/{filename}"}

    @staticmethod
    def _download_to(video_url: str, output_path: Path) -> None:
        session = requests.Session()
        retry = Retry(
            total=5,
            backoff_factor=1,
            status_forcelist=[500, 502, 503, 504],
            allowed_methods=["GET"],
        )
        session.mount("http://", HTTPAdapter(max_retries=retry))
        session.mount("https://", HTTPAdapter(max_retries=retry))
        headers = {
            "User-Agent": "Mozilla/5.0 (Windows NT 10.0; Win64; x64) AppleWebKit/537.36 Chrome/123.0 Safari/537.36",
            "Referer": "https://www.douyin.com/",
        }
        with session.get(video_url, headers=headers, stream=True, timeout=120) as response:
            response.raise_for_status()
            output_path.parent.mkdir(parents=True, exist_ok=True)
            with output_path.open("wb") as target:
                for chunk in response.iter_content(chunk_size=512 * 1024):
                    if chunk:
                        target.write(chunk)
