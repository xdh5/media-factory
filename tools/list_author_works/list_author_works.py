"""按作者主页拉取最新作品。只保留抖音用户作品列表这一段请求。"""

from __future__ import annotations

import base64
import json
import os
import random
import re
import time
import urllib.parse
from datetime import datetime, timezone

from pathlib import Path

import requests
from dotenv import load_dotenv
from tools.paths import PROJECT_ROOT

from ._a_bogus import ABogusPureSigner
from ._errors import AuthorWorksError, InvalidParameterError
from ._profile import get_profile
from ._web_sign import sign_url

# 从工厂读取采集配置。
load_dotenv(PROJECT_ROOT / ".env")

__all__ = ["list_author_works", "resolve_author_profile", "resolve_author_nickname"]

_SHORT_RE = re.compile(r"https?://v\.douyin\.com/[A-Za-z0-9_-]+/?", re.IGNORECASE)
_USER_PATH_RE = re.compile(r"/(?:share/)?user/([A-Za-z0-9_-]{8,128})", re.IGNORECASE)
_SEC_UID_RE = re.compile(r"[?&]sec_uid=([A-Za-z0-9_-]{8,128})", re.IGNORECASE)
_WEBID_RE = re.compile(r'user_unique_id\\?":\\?"(\d{6,})')
_SEC_USER_RE = re.compile(r"^[A-Za-z0-9_-]{8,128}$")
_SV_CHARSET = "0123456789ABCDEFGHIJKLMNOPQRSTUVWXYZabcdefghijklmnopqrstuvwxyz"
_PAGE_COUNT = 18
_MAX_CONSECUTIVE_EMPTY_PAGES = 10
_PAGE_ATTEMPTS = 3
_signer: ABogusPureSigner | None = None


def _signer_instance() -> ABogusPureSigner:
    global _signer
    if _signer is None:
        _signer = ABogusPureSigner(fixed=False)
    return _signer


def _cookies() -> dict[str, str]:
    raw = os.getenv("DY_COOKIES", "").strip()
    if not raw:
        raise AuthorWorksError(
            "缺少 DY_COOKIES。请在 .env 填入登录 www.douyin.com 后复制的完整 Cookie，且必须包含 UIFID",
        )
    cookies: dict[str, str] = {}
    for item in raw.split(";"):
        name, separator, value = item.strip().partition("=")
        if name and separator:
            cookies[name] = value
    if not cookies.get("UIFID"):
        raise AuthorWorksError("DY_COOKIES 缺少 UIFID，作者作品列表会被风控拦截")
    return cookies


def _ms_token(cookies: dict[str, str]) -> str:
    existing = cookies.get("msToken", "").strip()
    if existing:
        return existing
    alphabet = "ABCDEFGHIGKLMNOPQRSTUVWXYZabcdefghigklmnopqrstuvwxyz0123456789="
    return "".join(random.choice(alphabet) for _ in range(107))


def _verify_fp(cookies: dict[str, str]) -> str:
    existing = cookies.get("s_v_web_id", "").strip()
    if existing:
        return existing
    number = int(time.time() * 1000)
    base36 = ""
    while number:
        number, remainder = divmod(number, 36)
        base36 = "0123456789abcdefghijklmnopqrstuvwxyz"[remainder] + base36

    def chunk(length: int) -> str:
        return "".join(random.choice(_SV_CHARSET) for _ in range(length))

    groups = [chunk(8), chunk(4), "4" + chunk(3), random.choice("89ab") + chunk(3), chunk(12)]
    return "verify_" + base36 + "_" + "_".join(groups)


def _sec_user_id(text: str) -> str:
    """从主页、分享落地页或 sec_uid 参数里取出作者标识。路径优先于查询参数。"""
    matched = _USER_PATH_RE.search(text) or _SEC_UID_RE.search(text)
    if not matched:
        return ""
    return urllib.parse.unquote(matched.group(1))


def resolve_author_profile(profile_text: str) -> dict:
    """把作者主页、分享口令或 sec_user_id 规范成主页地址。短链会先跟随跳转。"""
    text = str(profile_text or "").strip()
    if not text:
        raise InvalidParameterError("profile_url", "作者主页链接不能为空")
    short = _SHORT_RE.search(text)
    if short:
        short_url = short.group(0)
        try:
            response = requests.get(
                short_url,
                headers={"User-Agent": get_profile()["ua"]},
                allow_redirects=True,
                timeout=20,
            )
            response.raise_for_status()
        except requests.RequestException as extra:
            raise AuthorWorksError(f"作者短链无法打开：{extra}", {"profile_url": short_url}) from extra
        text = str(response.url)
    if _SEC_USER_RE.fullmatch(text) and text.startswith("MS4w"):
        sec_user_id = text
    else:
        sec_user_id = _sec_user_id(text)
        if not sec_user_id:
            raise InvalidParameterError(
                "profile_url",
                "请提供抖音作者主页或「查看TA的更多作品」分享口令，不要用单条作品链接",
            )
    if not _SEC_USER_RE.fullmatch(sec_user_id):
        raise InvalidParameterError("profile_url", "作者主页链接里的 sec_user_id 格式不正确")
    return {
        "sec_user_id": sec_user_id,
        "profile_url": f"https://www.douyin.com/user/{sec_user_id}",
    }


def resolve_author_nickname(profile_url: str) -> str:
    """直接读取作者资料中的昵称，不依赖作品列表或作者是否发布作品。"""
    author = resolve_author_profile(profile_url)
    try:
        response = requests.get(
            "https://www.douyin.com/aweme/v1/web/user/profile/other/",
            params={
                "device_platform": "webapp",
                "aid": "6383",
                "sec_user_id": author["sec_user_id"],
            },
            headers={
                "User-Agent": get_profile()["ua"],
                "Referer": author["profile_url"],
            },
            cookies=_cookies(),
            timeout=20,
        )
        response.raise_for_status()
    except requests.RequestException as extra:
        raise AuthorWorksError("作者资料请求失败", {"profile_url": author["profile_url"]}) from extra
    if not response.content:
        raise AuthorWorksError(f"作者资料返回空响应（HTTP {response.status_code}）")
    try:
        payload = response.json()
    except ValueError as extra:
        raise AuthorWorksError("作者资料返回了无法解析的 JSON") from extra
    if not isinstance(payload, dict) or payload.get("status_code") != 0:
        raise AuthorWorksError("作者资料接口返回失败状态")
    user = payload.get("user")
    if not isinstance(user, dict) or user.get("sec_uid") != author["sec_user_id"]:
        raise AuthorWorksError("作者资料缺少匹配的作者 ID，未采用返回的昵称")
    nickname = str(user.get("nickname") or "").strip()
    if not nickname:
        raise AuthorWorksError("作者资料没有返回昵称")
    return nickname


def _webid(profile_url: str, cookies: dict[str, str]) -> str:
    profile = get_profile()
    try:
        response = requests.get(
            profile_url,
            headers={
                "user-agent": profile["ua"],
                "accept": "text/html,application/xhtml+xml,application/xml;q=0.9,*/*;q=0.8",
                "accept-language": profile["accept_language"],
            },
            cookies=cookies,
            timeout=20,
        )
        matched = _WEBID_RE.search(response.text or "")
        if matched:
            return matched.group(1)
    except requests.RequestException:
        pass
    # 主页受校验时可能拿不到 webid。随机生成的值会导致作品接口返回空响应。
    # 留空交给服务端处理，不能伪造一个与当前 Cookie 无关的浏览器标识。
    return ""


def _check_risk(response: requests.Response) -> None:
    text = (response.text or "").lstrip()
    if text.startswith("{") or text.startswith("["):
        return
    log_id = response.headers.get("X-Tt-Logid", "")
    challenge = response.headers.get("X-Vc-Bdturing-Parameters")
    if challenge:
        subtype = ""
        try:
            info = json.loads(base64.b64decode(challenge + "=" * (-len(challenge) % 4)))
            subtype = str(info.get("subtype") or "")
        except (json.JSONDecodeError, ValueError):
            subtype = ""
        raise AuthorWorksError(
            f"作者作品列表触发人机验证（{subtype or '未知类型'}）。请在浏览器完成验证，或降低请求频率后重试",
            {"log_id": log_id},
        )
    if not text:
        raise AuthorWorksError(
            f"作者作品列表返回空响应（HTTP {response.status_code}），通常是 Cookie 失效或签名被拦截",
            {"log_id": log_id},
        )
    raise AuthorWorksError(
        f"作者作品列表返回了无法解析的内容（HTTP {response.status_code}）",
        {"log_id": log_id, "preview": text[:120]},
    )


def _cover_url(item: dict) -> str:
    video = item.get("video") if isinstance(item.get("video"), dict) else {}
    for key in ("origin_cover", "cover", "dynamic_cover"):
        urls = (video.get(key) or {}).get("url_list") or []
        if urls:
            return str(urls[0])
    return ""


def _is_video(item: dict) -> bool:
    if item.get("is_ads") or item.get("ad_aweme"):
        return False
    if item.get("aweme_type") == 68:
        return False
    images = item.get("images")
    if isinstance(images, list) and images:
        return False
    play_urls = ((item.get("video") or {}).get("play_addr") or {}).get("url_list") or []
    return any(str(url).startswith("http") for url in play_urls)


def _published_at(item: dict) -> str:
    try:
        timestamp = int(item.get("create_time") or 0)
    except (TypeError, ValueError):
        return ""
    if timestamp <= 0:
        return ""
    return datetime.fromtimestamp(timestamp, timezone.utc).strftime("%Y-%m-%dT%H:%M:%SZ")


def _work(item: dict, sec_user_id: str) -> dict | None:
    aweme_id = str(item.get("aweme_id") or "").strip()
    if not aweme_id.isdigit():
        return None
    author = item.get("author") if isinstance(item.get("author"), dict) else {}
    title = str(item.get("desc") or "").strip()
    return {
        "aweme_id": aweme_id,
        "work_url": f"https://www.douyin.com/video/{aweme_id}",
        "title": title,
        "description": title,
        "duration_seconds": float((item.get("video") or {}).get("duration") or 0) / 1000,
        "author_name": str(author.get("nickname") or "").strip(),
        "sec_user_id": str(author.get("sec_uid") or sec_user_id),
        "published_at": _published_at(item),
        "cover_url": _cover_url(item),
        "is_video": _is_video(item),
    }


def _request_page(profile_url: str, sec_user_id: str, max_cursor: str, cookies: dict[str, str], webid: str) -> dict:
    profile = get_profile()
    params = [
        ("device_platform", "webapp"),
        ("aid", "6383"),
        ("channel", "channel_pc_web"),
        ("sec_user_id", sec_user_id),
        ("max_cursor", max_cursor),
        ("locate_query", "false"),
        ("show_live_replay_strategy", "1"),
        ("need_time_list", "1" if max_cursor == "0" else "0"),
        ("time_list_query", "0"),
        ("whale_cut_token", ""),
        ("cut_version", "1"),
        ("count", str(_PAGE_COUNT)),
        ("publish_video_strategy_type", "2"),
        ("from_user_page", "1"),
        ("update_version_code", "170400"),
        ("pc_client_type", "1"),
        ("pc_libra_divert", "Windows"),
        ("support_h265", "1"),
        ("support_dash", "1"),
        ("cpu_core_num", profile["cpu_core_num"]),
        ("version_code", "290100"),
        ("version_name", "29.1.0"),
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
        ("webid", webid),
        ("uifid", cookies["UIFID"]),
        ("msToken", _ms_token(cookies)),
    ]
    signed_query = "&".join(
        f"{key}={urllib.parse.quote(str(value), safe='')}" for key, value in params
    )
    params.append(("a_bogus", _signer_instance().sign_query(signed_query, "", host="www.douyin.com")))
    verify_fp = _verify_fp(cookies)
    params.extend([("verifyFp", verify_fp), ("fp", verify_fp)])
    raw_query = "&".join(f"{key}={value}" for key, value in params)
    url = sign_url(
        f"https://www.douyin.com/aweme/v1/web/aweme/post/?{raw_query}",
        uifid=cookies["UIFID"],
    )
    headers = {
        "user-agent": profile["ua"],
        "accept": "application/json, text/plain, */*",
        "sec-ch-ua": profile["sec_ch_ua"],
        "sec-ch-ua-mobile": "?0",
        "sec-ch-ua-platform": profile["sec_ch_ua_platform"],
        "accept-language": profile["accept_language"],
        "priority": "u=1, i",
        "sec-fetch-dest": "empty",
        "sec-fetch-mode": "cors",
        "sec-fetch-site": "same-origin",
        "referer": profile_url,
        "uifid": cookies["UIFID"],
    }
    try:
        response = requests.get(url, headers=headers, cookies=cookies, timeout=20)
    except requests.RequestException as extra:
        raise AuthorWorksError(f"作者作品列表请求失败：{extra}", {"profile_url": profile_url}) from extra
    _check_risk(response)
    try:
        payload = response.json()
    except ValueError as extra:
        raise AuthorWorksError("作者作品列表返回了无法解析的 JSON", {"profile_url": profile_url}) from extra
    if not isinstance(payload, dict):
        raise AuthorWorksError("作者作品列表响应不是对象", {"profile_url": profile_url})
    if payload.get("status_code") != 0:
        raise AuthorWorksError("作者作品列表返回失败状态", {
            "profile_url": profile_url,
            "status_code": payload.get("status_code"),
        })
    return payload


def list_author_works(profile_url: str, limit: int) -> list[dict]:
    """按发布时间从新到旧返回作者作品，数量不超过 limit。"""
    if isinstance(limit, bool) or not isinstance(limit, int) or limit < 1 or limit > 1000:
        raise InvalidParameterError("limit", "limit 必须是 1 到 1000 的整数")
    author = resolve_author_profile(profile_url)
    cookies = _cookies()
    webid = _webid(author["profile_url"], cookies)
    works: list[dict] = []
    max_cursor = "0"
    seen_cursors = set()
    empty_page_count = 0
    while len(works) < limit:
        if max_cursor in seen_cursors:
            break
        seen_cursors.add(max_cursor)
        for attempt in range(_PAGE_ATTEMPTS):
            payload = _request_page(
                author["profile_url"], author["sec_user_id"], max_cursor, cookies, webid,
            )
            page = payload.get("aweme_list")
            if isinstance(page, list) and payload.get("has_more") in (0, 1):
                break
            if attempt + 1 == _PAGE_ATTEMPTS:
                raise AuthorWorksError(
                    "作者作品分页响应不完整，同一游标重试后仍失败；不能将已读取作品当作完整列表。"
                    "请检查当前进程使用的 DY_COOKIES 配置来源及登录状态",
                    {"read_count": len(works), "max_cursor": max_cursor,
                     "attempts": _PAGE_ATTEMPTS, "response_keys": sorted(payload),
                     "has_more": payload.get("has_more"), "page_type": type(page).__name__},
                )
            time.sleep(attempt + 1)
        if not page:
            if payload.get("has_more") == 0:
                break
            # 隐藏或不可见作品可能形成空页；只有游标继续前进时才允许跳过。
            empty_page_count += 1
            if empty_page_count >= _MAX_CONSECUTIVE_EMPTY_PAGES:
                raise AuthorWorksError("作者作品列表连续空页超过限制，扫描中断", {
                    "read_count": len(works), "max_cursor": max_cursor,
                    "next_cursor": payload.get("max_cursor"),
                })
        else:
            empty_page_count = 0
        for item in page:
            if not isinstance(item, dict):
                continue
            work = _work(item, author["sec_user_id"])
            if work is None:
                continue
            works.append(work)
            if len(works) >= limit:
                break
        if len(works) >= limit or payload.get("has_more") != 1:
            break
        max_cursor = str(payload.get("max_cursor") or "")
        if not max_cursor or max_cursor == "0" or max_cursor in seen_cursors:
            raise AuthorWorksError("作者作品列表仍有下一页但翻页游标无效，扫描中断", {"read_count": len(works)})
    return works
