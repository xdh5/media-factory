"""检查浏览器真实发布页、缓存账号状态并接收宿主复核。"""

from __future__ import annotations

import threading
import time


from ._constants import (
    MEDIA_PUBLISHER_CODE_PLATFORMS,
    MEDIA_PUBLISHER_PLATFORM_CODES,
)
from ._errors import PublishAccountGroupError
from .publisher_cli import run_publisher_cli


_ACCOUNT_ROWS_CACHE: dict[tuple, tuple[float, list]] = {}
_ACCOUNT_ROWS_LOCK = threading.Lock()


def clear_account_rows_cache(account_ref: str) -> None:
    with _ACCOUNT_ROWS_LOCK:
        for key in list(_ACCOUNT_ROWS_CACHE):
            if key[0] == account_ref:
                _ACCOUNT_ROWS_CACHE.pop(key, None)


def probe_browser_accounts(account_refs: list[str] | None = None, *, platforms: list[str] | None = None,
                            refresh: bool = False) -> list:
    rows = []
    for group in account_refs if account_refs is not None else ("finance", "korean"):
        with _ACCOUNT_ROWS_LOCK:
            key = (group, tuple(sorted(platforms or [])))
            cached = _ACCOUNT_ROWS_CACHE.get(key)
            if (not refresh and cached and time.monotonic() - cached[0] < (300 if any(row.get("hostReviewed") for row in cached[1]) else 30)
                    and all(item.get("loggedIn") is True and item.get("realSessionProbe") is True for item in cached[1])):
                rows.extend(cached[1])
                continue
            arguments = ["accounts", "--json", "--phone", group]
            if platforms:
                arguments.extend(["--platforms", ",".join(MEDIA_PUBLISHER_PLATFORM_CODES[platform] for platform in platforms)])
            payload = run_publisher_cli(arguments)
            chunk = payload if isinstance(payload, list) else payload.get("accounts", [])
            if isinstance(chunk, list):
                _ACCOUNT_ROWS_CACHE[key] = (time.monotonic(), chunk)
                rows.extend(chunk)
    return rows


def list_publisher_accounts(account_refs: list[str] | None = None, *, rows: list | None = None) -> list[dict]:
    rows = probe_browser_accounts(account_refs) if rows is None else rows
    accounts = []
    for item in rows:
        if not isinstance(item, dict):
            continue
        raw_platform = str(item.get("pt") or item.get("platform") or "").strip()
        platform = MEDIA_PUBLISHER_CODE_PLATFORMS.get(raw_platform, raw_platform)
        group = str(item.get("phone") or item.get("account_group") or item.get("group") or "").strip()
        if platform not in MEDIA_PUBLISHER_PLATFORM_CODES or not group:
            continue
        if item.get("loggedIn") is not True or item.get("realSessionProbe") is not True:
            continue
        accounts.append({
            "platform": platform,
            "connector": "media-publisher",
            "account_id": group,
            "account_ref": group,
            "display_name": str(item.get("name") or item.get("title") or group),
            "login_status": "connected" if item.get("loggedIn") is True else str(item.get("status") or item.get("login_status") or "unknown"),
            "checked_at": item.get("checkedAt"),
            "real_session_probe": True,
            "raw": item,
        })
    return accounts


def list_publisher_login_states(*, rows: list | None = None) -> list[dict]:
    """返回真实发布页检测结果，明确区分需要登录和检测失败。"""
    rows = probe_browser_accounts() if rows is None else rows
    states = []
    for item in rows:
        if not isinstance(item, dict):
            continue
        raw_platform = str(item.get("pt") or item.get("platform") or "").strip()
        platform = MEDIA_PUBLISHER_CODE_PLATFORMS.get(raw_platform, raw_platform)
        account_ref = str(item.get("phone") or item.get("account_group") or item.get("group") or "").strip()
        if platform not in MEDIA_PUBLISHER_PLATFORM_CODES or not account_ref:
            continue
        logged_in = item.get("loggedIn") if item.get("realSessionProbe") is True else None
        login_required = item.get("loginRequired") is True
        states.append({
            "platform": platform,
            "account_ref": account_ref,
            "logged_in": logged_in,
            "status": "connected" if logged_in is True else "login_required" if login_required else "error",
            "reason": str(item.get("reason") or ""),
            "checked_at": item.get("checkedAt"),
            "real_session_probe": item.get("realSessionProbe") is True,
            "login_required": login_required,
            "screenshot_path": item.get("screenshotPath"),
            "current_url": item.get("currentUrl"),
            "login_tool": "publishing_start_login" if login_required else None,
        })
    return states


def review_publish_session(account_ref: str, platform: str, screenshot_path: str, ready: bool, reason: str) -> dict:
    """宿主查看真实发布页截图后提交判断，仅接纳近期自动检测不确定的页面。"""
    if not reason.strip():
        raise PublishAccountGroupError("必须说明页面可用或异常的可见依据")
    matches = []
    with _ACCOUNT_ROWS_LOCK:
        for key, (checked, rows) in _ACCOUNT_ROWS_CACHE.items():
            if key[0] != account_ref or time.monotonic() - checked >= 300:
                continue
            for row in rows:
                if (MEDIA_PUBLISHER_CODE_PLATFORMS.get(row.get("pt"), row.get("pt")) == platform
                        and row.get("screenshotPath") == screenshot_path
                        and row.get("loginRequired") is not True and row.get("status") == "error"):
                    matches.append(row)
        if not matches:
            raise PublishAccountGroupError("没有匹配的近期异常截图，请重新检测账号")
        for row in matches:
            row.update(hostReviewed=True, loggedIn=ready, status="connected" if ready else "error", reason=reason)
    return {"platform": platform, "account_ref": account_ref, "ready": ready, "reason": reason}


def cache_account_probe_rows(rows: list) -> None:
    with _ACCOUNT_ROWS_LOCK:
        for account_ref in {row["phone"] for row in rows}:
            selected_rows = [row for row in rows if row["phone"] == account_ref]
            selected_platforms = tuple(sorted({MEDIA_PUBLISHER_CODE_PLATFORMS.get(row["pt"], row["pt"]) for row in selected_rows}))
            _ACCOUNT_ROWS_CACHE[(account_ref, selected_platforms)] = (time.monotonic(), selected_rows)
