"""合并数据库配置、官方授权和浏览器预检结果。"""

from __future__ import annotations

import sys
import time

from core.tools.media_records import list_publishing_account_groups

from ._constants import (
    media_publisher_root,
)
from ._errors import PublishAccountGroupError
from .content import normalize_platforms
from .browser_accounts import cache_account_probe_rows, list_publisher_accounts, list_publisher_login_states, probe_browser_accounts
from .publisher_cli import run_publisher_cli


def load_database_groups(business_line: str | None = None) -> list[dict]:
    payload = list_publishing_account_groups(business_line=business_line)
    members_by_group: dict[str, list[dict]] = {}
    for member in payload["members"]:
        members_by_group.setdefault(str(member["group_code"]), []).append(dict(member))
    return [
        {**group, "source": "database", "members": members_by_group.get(str(group["code"]), [])}
        for group in payload["groups"]
    ]


def list_account_groups(business_line: str | None = None, account_group: str | None = None,
                        platforms: list[str] | None = None) -> dict:
    """只读取并筛选数据库账号组配置，不打开浏览器或检查授权。"""
    database = load_database_groups(None)
    requested = set(normalize_platforms(platforms)) if platforms is not None else None
    groups = [{**item, "members": [member for member in item["members"] if member["enabled"]
                                  and (requested is None or member["platform"] in requested)]}
              for item in database if (not business_line or item["business_line"] == business_line)
              and (not account_group or item["name"] == account_group) and item["enabled"]]
    return {"groups": groups}


def check_account_groups(business_line: str, account_group: str, platforms: list[str], progress=None) -> dict:
    """按平台执行真实账号预检，逐项报告进度与检测结果。"""
    groups = list_account_groups(business_line, account_group, platforms)["groups"]
    rows, errors = [], []
    for group in groups:
        live = []
        for member in group["members"]:
            label = f"{member['platform']} / {member['account_ref']}"
            if progress:
                progress(f"正在预检 {label}：打开真实发布页或验证官方授权")
            started = time.monotonic()
            try:
                if member["connector"] == "media-publisher":
                    detected = probe_browser_accounts([member["account_ref"]], platforms=[member["platform"]], refresh=True)
                    rows.extend(detected)
                    live.extend(list_publisher_accounts(rows=detected))
                else:
                    live.extend(_official_members(member))
                if progress:
                    progress(f"已完成预检 {label}（{time.monotonic() - started:.1f} 秒）")
            except Exception as exc:
                error = f"{label}：{type(exc).__name__}: {exc}"
                errors.append(error)
                if progress:
                    progress(f"预检失败 {error}")
        group["publisher_accounts"] = live
    cache_account_probe_rows(rows)
    return {"groups": groups, "publisher_login_states": list_publisher_login_states(rows=rows),
            "publisher_error": "；".join(errors) if errors else None}


_OFFICIAL_ACCOUNT_CACHE: dict[str, list] = {}


def _official_account_rows(group: str) -> list:
    if group not in _OFFICIAL_ACCOUNT_CACHE:
        payload = run_publisher_cli(["accounts", "--json", "--phone", group, "--official"])
        rows = payload if isinstance(payload, list) else payload.get("accounts", [])
        _OFFICIAL_ACCOUNT_CACHE[group] = rows if isinstance(rows, list) else []
    return _OFFICIAL_ACCOUNT_CACHE[group]


def _official_members(member: dict) -> list[dict]:
    if member.get("account_key"):
        python_dir = str(media_publisher_root() / "python")
        if python_dir not in sys.path:
            sys.path.insert(0, python_dir)
        from platform_api.account_registry import verify_account
        route = {**member, "account_id": member["connector_account_id"], "account_group": member["account_ref"]}
        try:
            return [{**route, **verify_account(member)}]
        except Exception as exc:
            return [{**route, "login_status": "error", "error": str(exc)}]
    platform = str(member["platform"])
    account_ref = str(member.get("account_ref") or "").strip()
    display_name = str(member.get("display_name") or account_ref)
    stored_platform_account_id = str(member.get("platform_account_id") or "").strip()
    if not stored_platform_account_id:
        raise PublishAccountGroupError(
            f"账号组成员 {member['group_code']}/{platform} 缺少 platform_account_id，不能发布",
            {"group_code": member["group_code"], "platform": platform},
        )

    def verified(row: dict, connector_account_id: str, current_platform_account_id: str) -> dict:
        actual = str(current_platform_account_id or "").strip()
        if actual != stored_platform_account_id:
            raise PublishAccountGroupError(
                f"账号组成员 {member['group_code']}/{platform} 的真实账号 ID 与当前授权账号不一致",
                {
                    "group_code": member["group_code"],
                    "platform": platform,
                    "stored_platform_account_id": stored_platform_account_id,
                    "current_platform_account_id": actual,
                },
            )
        return {
            **member,
            **row,
            "account_id": connector_account_id,
            "platform_account_id": stored_platform_account_id,
        }

    rows = [
        row for row in _official_account_rows(account_ref)
        if str(row.get("platform") or "") == platform
    ]
    return [
        verified(
            {"display_name": row.get("display_name") or display_name},
            str(row.get("account_id") or ""),
            str(row.get("platform_account_id") or ""),
        )
        for row in rows
        if isinstance(row, dict)
    ]


def resolve_account_group(account_group: str, business_line: str, platforms: list[str]) -> list[dict]:
    requested = set(platforms)
    database = load_database_groups(None)
    known_group = next(
        (item for item in database if str(item["name"]) == account_group),
        None,
    )
    selected = known_group if known_group and known_group["business_line"] == business_line else None
    if selected is None and known_group is not None:
        raise PublishAccountGroupError(
            f"账号组“{account_group}”属于 {known_group['business_line']}，不能用于 {business_line}",
            {"account_group": account_group, "expected_business_line": known_group["business_line"]},
        )
    account_refs = sorted({member["account_ref"] for member in selected["members"]
                           if member["platform"] in requested and member["connector"] == "media-publisher"
                           and member["enabled"]}) if selected else []
    rows = []
    for account_ref in account_refs:
        browser_platforms = sorted({member["platform"] for member in selected["members"]
                                    if member["account_ref"] == account_ref and member["platform"] in requested
                                    and member["connector"] == "media-publisher" and member["enabled"]})
        rows.extend(probe_browser_accounts([account_ref], platforms=browser_platforms))
    live_matrix = list_publisher_accounts(rows=rows)
    if selected:
        routes = []
        for member in selected["members"]:
            if member["platform"] not in requested or not member["enabled"]:
                continue
            if member["connector"] == "media-publisher":
                platform_account_id = str(member.get("platform_account_id") or "").strip()
                if not platform_account_id:
                    raise PublishAccountGroupError(
                        f"账号组成员 {member['group_code']}/{member['platform']} 缺少 platform_account_id，不能发布",
                        {"group_code": member["group_code"], "platform": member["platform"]},
                    )
                matches = [
                    {**item, "platform_account_id": platform_account_id} for item in live_matrix
                    if item["platform"] == member["platform"]
                    and item["account_ref"] == member["account_ref"]
                ]
                routes.extend(matches)
            else:
                routes.extend(_official_members(member))
    else:
        raise PublishAccountGroupError(
            f"找不到数据库账号组“{account_group}”；未入库的 media-publisher 登录态不能直接用于发布",
            {"account_group": account_group},
        )
    unavailable = [item for item in routes if item.get("login_status") != "connected"]
    routes = [item for item in routes if item.get("login_status") == "connected"]
    missing = sorted(requested - {str(item["platform"]) for item in routes})
    if missing:
        account_states = list_publisher_login_states(rows=rows)
        login_required = [
            {
                "platform": state["platform"],
                "account_ref": state["account_ref"],
                "login_tool": "publishing_start_login",
            }
            for state in account_states if state["platform"] in missing and state["login_required"]
        ]
        reasons = [f"{state['platform']}：{state['reason']}" for state in account_states if state["platform"] in missing]
        action = "请先登录上述失效账号，再重新预检" if login_required else "请先处理页面或网络检测错误，再重新预检"
        raise PublishAccountGroupError(
            f"账号组“{account_group}”发布前账号预检未通过：{'；'.join(reasons) or ', '.join(missing)}。{action}",
            {
                "account_group": account_group,
                "missing_platforms": missing,
                "login_required": login_required,
                "account_states": account_states,
                "inspection_errors": [state for state in account_states if state["status"] == "error"] + unavailable,
                "next_step": "仅对 login_required 调用扫码登录；检测失败先处理页面或网络问题，再重新预检",
            },
        )
    return routes
