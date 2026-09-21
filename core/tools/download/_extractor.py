"""yt-dlp 解析封装：链接 -> 最佳视频流 + 防盗链请求头。

移植自 xingchen-video-download 的 app/extractor.py，async 改为同步。
路由规则：
  - 微信视频号 -> _wechat.py（腾讯元宝，需要 SPH_COOKIE）
  - 其他平台   -> yt-dlp（覆盖 1000+ 站点）
每个视频流自带 http_headers（Referer + UA + Cookie），下载时必须原样回放，
否则抖音/B 站等 CDN 的防盗链校验会 403。
"""

from __future__ import annotations

import logging
import os
import re
from dataclasses import dataclass, field
from typing import Any

from yt_dlp import YoutubeDL
from yt_dlp.utils import DownloadError as YtdlpDownloadError
from yt_dlp.utils import UnsupportedError

from . import _cookies as ck
from ._constants import (
    DEFAULT_UA,
    PARSE_SOCKET_TIMEOUT_SECONDS,
    PLATFORM_NAMES,
    PLATFORM_REFERER,
)
from ._douyin import fetch_video as fetch_douyin
from ._errors import ParseLinkError
from ._urlutil import detect_platform, extract_url
from ._wechat import VideoInfo, fetch_video as fetch_wechat

logger = logging.getLogger("media-factory.download.extractor")

SPH_PATTERN = re.compile(r"weixin\.qq\.com/(?:sph|channel|finder)/", re.I)


@dataclass
class ResolvedVideo:
    """一次解析的结果：视频流地址、可选的独立音轨地址和必须回放的请求头。"""

    platform: str
    platform_name: str
    video_id: str
    title: str
    cover_url: str
    video_url: str
    headers: dict[str, str] = field(default_factory=dict)
    audio_url: str = ""
    ext: str = "mp4"


def _https(url: str) -> str:
    if url and url.startswith("http://"):
        return "https://" + url[len("http://"):]
    return url


def _to_resolved(data: dict, platform: str) -> ResolvedVideo:
    """把专用解析器（抖音/视频号）的字段字典转成 ResolvedVideo。"""
    return ResolvedVideo(
        platform=platform,
        platform_name=PLATFORM_NAMES.get(platform, platform),
        video_id=str(data.get("video_id") or ""),
        title=data.get("title") or "未命名视频",
        cover_url=_https(data.get("cover_url") or ""),
        video_url=str(data.get("video_url") or ""),
        headers=data.get("headers") or {},
        audio_url=data.get("audio_url") or "",
        ext=data.get("ext") or "mp4",
    )


def _pick_formats(info: dict) -> tuple[dict | None, dict | None]:
    """从 yt-dlp 信息里挑最佳视频流；音轨独立存在时一并返回。

    返回 (video, audio)，audio 可为 None。
    """
    formats = info.get("formats") or []
    # 优先选音视频合一的 mp4（progressive）。
    progressive = [
        f for f in formats
        if f.get("vcodec") not in (None, "none")
        and f.get("acodec") not in (None, "none")
        and f.get("ext") == "mp4"
        and f.get("url")
    ]
    if progressive:
        return max(progressive, key=lambda f: f.get("height") or 0), None
    # 其次选独立的视频轨 mp4；若 requested_formats 提供独立音轨则记录下来。
    requested = info.get("requested_formats")
    audio = None
    if isinstance(requested, list) and len(requested) >= 2:
        audio = requested[1] if requested[1].get("url") else None
    if not audio:
        audio_candidates = [
            f for f in formats
            if f.get("vcodec") in (None, "none") and f.get("acodec") not in (None, "none") and f.get("url")
        ]
        audio = max(audio_candidates, key=lambda f: f.get("abr") or 0) if audio_candidates else None
    video_mp4 = [
        f for f in formats
        if f.get("vcodec") not in (None, "none") and f.get("url") and f.get("ext") == "mp4"
    ]
    if video_mp4:
        return max(video_mp4, key=lambda f: f.get("height") or 0), audio
    # requested_formats 里的视频轨（音视频分轨时的标准形态）。
    if isinstance(requested, list) and requested and requested[0].get("url"):
        return requested[0], audio
    # 顶层 url（部分提取器直接给单流）。
    if info.get("url"):
        return info, audio
    raise ParseLinkError(
        "未找到可下载的视频流（可能是图文笔记，或需要登录 Cookie）。"
        "可在 data/download/cookies/<平台>.txt 放置 Netscape 格式 Cookie 后重试"
    )


def _extract_with_ytdlp(url: str, platform: str, cookie_header: str) -> ResolvedVideo:
    referer = PLATFORM_REFERER.get(platform) or url
    http_headers: dict[str, str] = {"User-Agent": DEFAULT_UA, "Referer": referer}
    opts: dict[str, Any] = {
        "quiet": True,
        "no_warnings": True,
        "skip_download": True,
        "noplaylist": True,
        "extract_flat": False,
        "ignoreerrors": False,
        "socket_timeout": PARSE_SOCKET_TIMEOUT_SECONDS,
        "http_headers": http_headers,
    }
    manual = ck.manual_cookie_file(platform)
    if manual:
        opts["cookiefile"] = str(manual)
    elif cookie_header:
        http_headers["Cookie"] = cookie_header

    try:
        with YoutubeDL(opts) as ydl:
            info = ydl.extract_info(url, download=False)
    except UnsupportedError:
        raise ParseLinkError("不支持的平台或链接格式，请检查链接是否完整") from None
    except YtdlpDownloadError as exc:
        message = str(exc).replace("ERROR: ", "").strip()
        if "Unsupported URL" in message:
            raise ParseLinkError("不支持的平台或链接格式，请检查链接是否完整") from exc
        if "geo-restricted" in message or "geo blocked" in message:
            raise ParseLinkError("该视频有地区限制，可能需要代理后重试") from exc
        if "Private video" in message:
            raise ParseLinkError("这是私密视频，无法下载") from exc
        if "No video formats found" in message or "obtain" in message.lower():
            raise ParseLinkError(
                "无法提取视频（可能是图文笔记，或需要登录 Cookie）。"
                f"请在 data/download/cookies/{platform}.txt 放置登录 Cookie 后重试"
            ) from exc
        if "cookies" in message.lower() or "login" in message.lower():
            raise ParseLinkError(
                "该内容需要登录，请在 data/download/cookies/"
                f"{platform}.txt 放置 Cookie（Netscape 格式）后重试"
            ) from exc
        raise ParseLinkError(f"解析失败：{message}") from exc
    except OSError as exc:
        raise ParseLinkError(f"解析请求失败：{exc}") from exc
    if not info:
        raise ParseLinkError("yt-dlp 未能提取视频信息")
    if info.get("_type") in ("playlist", "multi_video"):
        entries = info.get("entries") or []
        if not entries:
            raise ParseLinkError("播放列表为空，无法下载")
        info = entries[0]

    video_format, audio_format = _pick_formats(info)
    thumbnails = info.get("thumbnails") or []
    cover = info.get("thumbnail") or (
        thumbnails[-1].get("url") if thumbnails and thumbnails[-1].get("url") else ""
    )
    # 请求头按 优先级合并：视频流自带 > info 全局 > 平台默认。
    headers = dict(info.get("http_headers") or {})
    headers.update(video_format.get("http_headers") or {})
    headers.setdefault("User-Agent", DEFAULT_UA)
    headers.setdefault("Referer", referer)
    audio_url = ""
    if audio_format and audio_format.get("url"):
        audio_url = str(audio_format["url"])
    return ResolvedVideo(
        platform=platform,
        platform_name=PLATFORM_NAMES.get(platform, platform),
        video_id=str(info.get("id") or ""),
        title=info.get("title") or "未命名视频",
        cover_url=_https(cover or ""),
        video_url=str(video_format["url"]),
        headers=headers,
        audio_url=audio_url,
        ext=video_format.get("ext") or "mp4",
    )


def parse_share_text(raw_text: str, sph_cookie: str = "") -> ResolvedVideo:
    """分享文本 -> 视频流解析结果；视频号走元宝接口，其余走 yt-dlp。"""
    url = extract_url(raw_text)
    if not url:
        raise ParseLinkError(
            "未识别到链接，请粘贴包含 http/https 的分享口令或视频链接",
            {"share_text": raw_text},
        )
    platform = detect_platform(url)

    # 抖音：yt-dlp 的 web detail API 已被风控 403，改走移动端 feed 接口。
    if platform == "douyin":
        try:
            return _to_resolved(fetch_douyin(url), "douyin")
        except ParseLinkError:
            raise
        except Exception as exc:
            raise ParseLinkError(f"抖音解析失败：{exc}") from exc

    if platform == "wechat" or SPH_PATTERN.search(url):
        logger.info("WeChat Channels URL: %s", url)
        try:
            info = fetch_wechat(url, sph_cookie or os.getenv("SPH_COOKIE", ""))
        except ValueError as exc:
            message = str(exc)
            if "SPH_COOKIE" in message:
                raise ParseLinkError(
                    "微信视频号解析失败：未配置 Cookie。请在 .env 设置 SPH_COOKIE 后重试，"
                    "或选择其他平台"
                ) from exc
            raise ParseLinkError(f"微信视频号解析失败：{message}") from exc
        except Exception as exc:
            raise ParseLinkError(f"微信视频号解析失败：{exc}") from exc
        return ResolvedVideo(
            platform="wechat",
            platform_name=PLATFORM_NAMES["wechat"],
            video_id=info.video_id,
            title=info.title,
            cover_url=info.cover_url,
            video_url=info.video_url,
            headers=info.headers,
            ext=info.ext,
        )

    cookie_header = ck.get_cookie_header(platform)
    logger.info("yt-dlp extract: platform=%s url=%s cookie=%d chars",
                platform, url, len(cookie_header))
    return _extract_with_ytdlp(url, platform, cookie_header)
