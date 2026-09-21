"""平台 Cookie 管理：自动获取访客 Cookie + 可选手动 Cookie 文件。

移植自 xingchen-video-download 的 app/cookies.py，async httpx 改为同步 requests。
两层策略：
1. 自动（默认）：抓取访客 Cookie。多数平台 GET 一次首页即可（B 站下发 buvid3），
   抖音需要 POST 字节跳动 ttwid 注册接口（首页不下发有效 Cookie）。
2. 手动（可选）：`data/download/cookies/<platform>.txt`（Netscape 格式）优先于自动
   Cookie，用于会员视频或更高清晰度。
"""

from __future__ import annotations

import logging
import time
from pathlib import Path

import requests

from ._constants import DEFAULT_UA, MANUAL_COOKIE_DIR

logger = logging.getLogger("media-factory.download.cookies")

_CACHE: dict[str, tuple[str, float]] = {}
_CACHE_TTL_SECONDS = 6 * 3600

_HOMEPAGES = {
    "bilibili": "https://www.bilibili.com/",
    "weibo": "https://weibo.com/",
    "xhs": "https://www.xiaohongshu.com/",
    "youtube": "https://www.youtube.com/",
    "tiktok": "https://www.tiktok.com/",
}

_DOC_HEADERS = {
    "User-Agent": DEFAULT_UA,
    "Accept": "text/html,application/xhtml+xml,application/xml;q=0.9,*/*;q=0.8",
    "Accept-Language": "zh-CN,zh;q=0.9,en;q=0.8",
    "Sec-Fetch-Dest": "document",
    "Sec-Fetch-Mode": "navigate",
    "Sec-Fetch-Site": "none",
    "Upgrade-Insecure-Requests": "1",
}


def manual_cookie_file(platform: str) -> Path | None:
    path = MANUAL_COOKIE_DIR / f"{platform}.txt"
    return path if path.is_file() else None


def _load_manual_cookies(platform: str) -> str:
    path = manual_cookie_file(platform)
    if not path:
        return ""
    pairs: list[str] = []
    for line in path.read_text(encoding="utf-8").splitlines():
        line = line.strip()
        if not line or line.startswith("#") or line.startswith("HttpOnly_"):
            continue
        parts = line.split("\t")
        if len(parts) < 7:
            continue
        name, value = parts[5], parts[6]
        if name:
            pairs.append(f"{name}={value}")
    return "; ".join(pairs)


def _fetch_homepage_cookies(platform: str) -> str:
    """带文档头 GET 首页，B 站会以这种方式下发 buvid3。"""
    url = _HOMEPAGES.get(platform)
    if not url:
        return ""
    response = requests.get(url, headers=_DOC_HEADERS, timeout=20, allow_redirects=True)
    pairs = [f"{k}={v}" for k, v in response.cookies.items()]
    logger.info("homepage cookies for %s: %s", platform, list(response.cookies.keys()))
    return "; ".join(pairs)


def _fetch_douyin_cookies() -> str:
    """抖音需要从字节跳动 ttwid 注册接口拿访客 Cookie（无需 JS）。"""
    payload = {
        "region": "cn", "aid": 1768, "needFid": False,
        "service": "www.douyin.com",
        "migrate_info": {"ticket": "", "source": "node"},
        "cbUrlProtocol": "https", "union": True,
    }
    response = requests.post(
        "https://ttwid.bytedance.com/ttwid/union/register/",
        json=payload,
        headers={"Content-Type": "application/json", "User-Agent": DEFAULT_UA},
        timeout=20,
    )
    ttwid = response.cookies.get("ttwid", "")
    if ttwid:
        logger.info("douyin ttwid fetched (%d chars)", len(ttwid))
        return f"ttwid={ttwid}"
    logger.warning("douyin ttwid fetch failed: status %s", response.status_code)
    return ""


def _fetch_visitor_cookies(platform: str) -> str:
    if platform == "douyin":
        return _fetch_douyin_cookies()
    return _fetch_homepage_cookies(platform)


def get_cookie_header(platform: str) -> str:
    """返回指定平台当前可用的 Cookie 头，手动文件 > 缓存 > 实时抓取。"""
    manual = _load_manual_cookies(platform)
    if manual:
        logger.info("using manual cookies for %s (%d chars)", platform, len(manual))
        return manual

    now = time.time()
    cached = _CACHE.get(platform)
    if cached and now < cached[1]:
        return cached[0]

    try:
        fresh = _fetch_visitor_cookies(platform)
    except Exception as exc:  # 访客 Cookie 抓取失败不阻断解析，退回无 Cookie。
        logger.warning("visitor cookie fetch failed for %s: %s", platform, exc)
        fresh = ""
    if fresh:
        _CACHE[platform] = (fresh, now + _CACHE_TTL_SECONDS)
    return fresh
