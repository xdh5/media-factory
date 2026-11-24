"""抖音解析：分享短链 -> 作品数据 -> 无水印视频直链。

优先走移动端 feed，免 Cookie、免签名。推荐流经常忽略指定作品并返回其他视频，
此时不能拿列表里的别的视频顶替，改走已登录的作品详情接口。详情接口需要
环境变量 DY_COOKIES，且必须包含 UIFID。
"""

from __future__ import annotations

import logging
import os
import random
import re
import time
import urllib.parse
from pathlib import Path
from urllib.parse import urlparse

import requests

from ._constants import PLATFORM_NAMES
from ._errors import ParseLinkError
from ._metadata import collect_topics

logger = logging.getLogger("download_video.douyin")

UA_MOBILE = (
    "Mozilla/5.0 (iPhone; CPU iPhone OS 13_2_3 like Mac OS X) "
    "AppleWebKit/605.1.15 (KHTML, like Gecko) Version/13.0.3 Mobile/15E148 Safari/604.1"
)

FEED_URL = "https://api.amemv.com/aweme/v1/feed/"
DETAIL_URL = "https://www.douyin.com/aweme/v1/web/aweme/detail/"
DETAIL_ATTEMPTS = 3

# 支持的抖音链接形态：主站视频/图文页、短链。
_AWEME_ID_RE = re.compile(r"/(?:video|note)/(\d+)")
_SLIDE_ID_RE = re.compile(r"/share/slides/(\d+)")


def _metadata(aweme: dict, video_id: str, author: str) -> tuple[str, str, list[str]]:
    """标题、描述和话题都取自作品原文，不改写。"""
    description = str(aweme.get("desc") or "").strip()
    item_title = str(aweme.get("item_title") or "").strip()
    if not description and not item_title:
        description = f"抖音作品 {video_id}" if not author else f"{author}的抖音作品"
    topics: list[str] = []
    seen: set[str] = set()
    for extra in aweme.get("text_extra") or []:
        if not isinstance(extra, dict):
            continue
        name = str(extra.get("hashtag_name") or "").strip().lstrip("#")
        if not name:
            continue
        tag = f"#{name}"
        if tag in seen:
            continue
        seen.add(tag)
        topics.append(tag)
    if not topics:
        topics = collect_topics(description)
    return item_title or description, description, topics


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


def _cookie_jar() -> dict[str, str]:
    """读取工厂采集配置。"""
    from dotenv import load_dotenv
    from tools.paths import PROJECT_ROOT

    load_dotenv(PROJECT_ROOT / ".env")
    raw = os.getenv("DY_COOKIES", "").strip()
    cookies: dict[str, str] = {}
    for item in raw.split(";"):
        name, separator, value = item.strip().partition("=")
        if name and separator:
            cookies[name] = value
    return cookies


def _ms_token(cookies: dict[str, str]) -> str:
    existing = cookies.get("msToken", "").strip()
    if existing:
        return existing
    alphabet = "ABCDEFGHIGKLMNOPQRSTUVWXYZabcdefghigklmnopqrstuvwxyz0123456789="
    return "".join(random.choice(alphabet) for _ in range(107))


def _aweme_from_feed(session: requests.Session, video_id: str) -> dict | None:
    """推荐流只有精确命中才采用。未收录时返回空，交给作品详情。"""
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
    aweme_list = body.get("aweme_list") or []
    aweme = next((item for item in aweme_list if isinstance(item, dict) and str(item.get("aweme_id")) == video_id), None)
    if aweme:
        return aweme
    logger.info(
        "douyin feed missed id=%s returned=%s",
        video_id,
        [str(item.get("aweme_id")) for item in aweme_list if isinstance(item, dict)][:5],
    )
    return None


def _detail_url(video_id: str, cookies: dict[str, str]) -> tuple[str, dict]:
    """按主站作品详情的签名规则生成可直接请求的 URL 和浏览器档案。"""
    from tools.list_author_works._a_bogus import ABogusPureSigner
    from tools.list_author_works._profile import get_profile
    from tools.list_author_works._web_sign import sign_url

    profile = get_profile()
    params = [
        ("device_platform", "webapp"),
        ("aid", "6383"),
        ("channel", "channel_pc_web"),
        ("aweme_id", video_id),
        ("update_version_code", "170400"),
        ("pc_client_type", "1"),
        ("pc_libra_divert", "Windows"),
        ("support_h265", "1"),
        ("support_dash", "0"),
        ("cpu_core_num", profile["cpu_core_num"]),
        ("version_code", "190500"),
        ("version_name", "19.5.0"),
        ("cookie_enabled", "true"),
        ("screen_width", profile["screen_width"]),
        ("screen_height", profile["screen_height"]),
        ("browser_language", "zh-CN"),
        ("browser_platform", "Win32"),
        ("browser_name", profile["browser_name"]),
        ("browser_version", profile["browser_version"]),
        ("browser_online", "true"),
        ("engine_name", "Blink"),
        ("engine_version", profile["engine_version"]),
        ("os_name", "Windows"),
        ("os_version", "10"),
        ("device_memory", profile["device_memory"]),
        ("platform", "PC"),
        ("downlink", "10"),
        ("effective_type", "4g"),
        ("round_trip_time", "0"),
        ("uifid", cookies["UIFID"]),
        ("msToken", _ms_token(cookies)),
    ]
    signed_query = "&".join(
        f"{key}={urllib.parse.quote(str(value), safe='')}" for key, value in params
    )
    params.append(("a_bogus", ABogusPureSigner(fixed=False).sign_query(signed_query, "", host="www.douyin.com")))
    verify = cookies.get("s_v_web_id", "").strip()
    if verify:
        params.extend([("verifyFp", verify), ("fp", verify)])
    raw_query = "&".join(f"{key}={value}" for key, value in params)
    url = sign_url(f"{DETAIL_URL}?{raw_query}", uifid=cookies["UIFID"])
    return url, profile


def _aweme_from_detail(video_id: str) -> dict:
    """推荐流未收录时，用登录 Cookie 向作品详情要这一条。"""
    cookies = _cookie_jar()
    if not cookies.get("UIFID"):
        raise ParseLinkError(
            "抖音推荐流未返回该作品，不能改用列表中的其他视频。作品详情需要 DY_COOKIES，且必须包含 UIFID",
            {"video_id": video_id},
        )
    last_error = "作品详情没有返回内容"
    for attempt in range(1, DETAIL_ATTEMPTS + 1):
        try:
            url, profile = _detail_url(video_id, cookies)
            response = requests.get(
                url,
                headers={
                    "user-agent": profile["ua"],
                    "accept": "application/json, text/plain, */*",
                    "referer": f"https://www.douyin.com/video/{video_id}",
                    "uifid": cookies["UIFID"],
                },
                cookies=cookies,
                timeout=20,
            )
        except requests.RequestException as exc:
            last_error = str(exc)
            time.sleep(attempt)
            continue
        if response.status_code != 200 or not response.content:
            last_error = f"HTTP {response.status_code}，响应长度 {len(response.content)}"
            time.sleep(attempt)
            continue
        try:
            body = response.json()
        except ValueError:
            last_error = f"HTTP {response.status_code}，响应不是 JSON"
            time.sleep(attempt)
            continue
        if not isinstance(body, dict):
            last_error = "作品详情响应不是对象"
            time.sleep(attempt)
            continue
        aweme = body.get("aweme_detail")
        if isinstance(aweme, dict) and str(aweme.get("aweme_id")) == video_id:
            logger.info("douyin detail resolved: id=%s", video_id)
            return aweme
        filtered = body.get("filter_detail") if isinstance(body.get("filter_detail"), dict) else {}
        if filtered:
            reason = filtered.get("detail_msg") or filtered.get("notice") or filtered.get("filter_reason") or "作品不可用"
            raise ParseLinkError(
                f"抖音作品详情拒绝返回该作品：{reason}",
                {"video_id": video_id, "filter_reason": filtered.get("filter_reason"), "status_code": body.get("status_code")},
            )
        last_error = f"status_code={body.get('status_code')}"
        time.sleep(attempt)
    raise ParseLinkError(
        f"抖音作品详情连续 {DETAIL_ATTEMPTS} 次未返回匹配作品：{last_error}",
        {"video_id": video_id},
    )


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
        aweme = _aweme_from_feed(session, video_id)
    except Exception as exc:
        raise ParseLinkError(f"抖音解析失败：{exc}", {"url": url}) from exc
    headers = {"User-Agent": UA_MOBILE, "Referer": "https://www.douyin.com/"}
    if aweme is None:
        aweme = _aweme_from_detail(video_id)
        from tools.list_author_works._profile import get_profile

        headers = {"User-Agent": get_profile()["ua"], "Referer": "https://www.douyin.com/"}

    video = aweme.get("video") or {}
    play_urls = (video.get("play_addr") or {}).get("url_list") or []
    video_urls = list(dict.fromkeys(str(item) for item in play_urls if str(item).startswith("http")))
    if video.get("play_addr"):
        # 接口返回的 CDN 节点可能单点回源失败，追加播放网关以便重新分配节点。
        uri = video["play_addr"].get("uri") or video["play_addr"].get("vid") or ""
        if uri:
            gateway_url = f"https://www.iesdouyin.com/aweme/v1/play/?video_id={uri}&ratio=1080p&line=0"
            if gateway_url not in video_urls:
                video_urls.append(gateway_url)
    if not video_urls:
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
    title, description, topics = _metadata(aweme, video_id, author)

    logger.info("douyin resolved: id=%s title=%s", video_id, title[:30])
    return {
        "platform": "douyin",
        "platform_name": PLATFORM_NAMES["douyin"],
        "video_id": str(aweme.get("aweme_id") or video_id),
        "title": title,
        "description": description,
        "topics": topics,
        "cover_url": cover_url,
        "video_url": video_urls[0],
        "video_urls": video_urls,
        # CDN 会校验拿到直链时使用的 UA，下载时必须原样回放。
        "headers": headers,
        "audio_url": "",
        "ext": "mp4",
    }
