"""抖音解析：分享短链 -> aweme feed 接口 -> 无水印视频直链。

yt-dlp 的抖音提取器走 www.douyin.com web detail API，该接口已被风控拦截（403），
因此这里直接调用移动端 feed 接口（免 Cookie、免签名），返回无水印 mp4 与封面。
"""

from __future__ import annotations

import logging
import re
from urllib.parse import urlparse

import requests

from ._constants import PLATFORM_NAMES
from ._errors import ParseLinkError

logger = logging.getLogger("media-factory.download.douyin")

UA_MOBILE = (
    "Mozilla/5.0 (iPhone; CPU iPhone OS 13_2_3 like Mac OS X) "
    "AppleWebKit/605.1.15 (KHTML, like Gecko) Version/13.0.3 Mobile/15E148 Safari/604.1"
)

FEED_URL = "https://api.amemv.com/aweme/v1/feed/"

# 支持的抖音链接形态：主站视频/图文页、短链。
_AWEME_ID_RE = re.compile(r"/(?:video|note)/(\d+)")
_SLIDE_ID_RE = re.compile(r"/share/slides/(\d+)")


def _extract_aweme_id(url: str) -> str:
    matched = _AWEME_ID_RE.search(url) or _SLIDE_ID_RE.search(url)
    if matched:
        return matched.group(1)
    return ""


def _expand_short_url(session: requests.Session, url: str) -> str:
    """v.douyin.com 短链跟随重定向拿到真实视频页地址。"""
    response = session.get(url, headers={"User-Agent": UA_MOBILE}, timeout=20, allow_redirects=True)
    response.raise_for_status()
    return str(response.url)


def fetch_video(url: str) -> dict:
    """解析抖音链接，返回 ResolvedVideo 兼容的字段字典。"""
    session = requests.Session()
    if "v.douyin.com" in urlparse(url).netloc:
        url = _expand_short_url(session, url)
    video_id = _extract_aweme_id(url)
    if not video_id:
        raise ParseLinkError(
            "未从抖音链接中识别出作品 ID，请确认是视频或图文分享链接",
            {"url": url},
        )

    try:
        response = session.get(
            FEED_URL,
            params={
                "aweme_id": video_id,
                "version_code": "11.4.0",
                "app_name": "aweme",
                "channel": "App Store",
                "device_platform": "iphone",
                "device_type": "iPhone9,1",
            },
            headers={"User-Agent": UA_MOBILE},
            timeout=20,
        )
        response.raise_for_status()
        body = response.json()
    except Exception as exc:
        raise ParseLinkError(f"抖音解析失败：{exc}", {"url": url}) from exc

    aweme_list = body.get("aweme_list") or []
    aweme = next((a for a in aweme_list if str(a.get("aweme_id")) == video_id), aweme_list[0] if aweme_list else None)
    if not aweme:
        raise ParseLinkError(
            "抖音接口未返回该作品，可能已被删除或设为私密",
            {"url": url, "video_id": video_id},
        )

    video = aweme.get("video") or {}
    play_urls = (video.get("play_addr") or {}).get("url_list") or []
    video_url = next((u for u in play_urls if u.startswith("http")), "")
    if not video_url and video.get("play_addr"):
        # 兜底：用 uri 构造播放直链。
        uri = video["play_addr"].get("uri") or video["play_addr"].get("vid") or ""
        if uri:
            video_url = f"https://www.iesdouyin.com/aweme/v1/play/?video_id={uri}&ratio=1080p&line=0"
    if not video_url:
        raise ParseLinkError(
            "抖音接口未返回视频地址，作品可能是图集或已下架",
            {"url": url, "video_id": video_id},
        )

    cover_url = ""
    for key in ("origin_cover", "cover", "dynamic_cover"):
        urls = (video.get(key) or {}).get("url_list") or []
        if urls:
            cover_url = urls[0]
            break

    author = (aweme.get("author") or {}).get("nickname") or ""
    title = aweme.get("desc") or (f"抖音作品 {video_id}" if not author else f"{author}的抖音作品")

    logger.info("douyin resolved: id=%s title=%s", video_id, title[:30])
    return {
        "platform": "douyin",
        "platform_name": PLATFORM_NAMES["douyin"],
        "video_id": str(aweme.get("aweme_id") or video_id),
        "title": title,
        "cover_url": cover_url,
        "video_url": video_url,
        # CDN 校验移动端 UA，下载时必须原样回放。
        "headers": {"User-Agent": UA_MOBILE, "Referer": "https://www.douyin.com/"},
        "audio_url": "",
        "ext": "mp4",
    }
