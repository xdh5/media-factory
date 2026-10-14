"""合并数据库账号组、官方账号和 MatrixMedia 本机账号。"""

from __future__ import annotations

import json
import os
import re
import shutil
import subprocess
import tempfile
import threading
import time
import uuid
from pathlib import Path

from core.tools.cloudflare_data import list_publishing_account_groups
from core.tools.publish_to_facebook import list_facebook_accounts
from core.tools.publish_to_instagram import list_instagram_accounts
from core.tools.publish_to_tiktok import list_tiktok_accounts
from core.tools.publish_to_youtube import list_youtube_accounts

from ._constants import (
    MATRIXMEDIA_CODE_PLATFORMS,
    MATRIXMEDIA_DIR_ENV,
    MATRIXMEDIA_EXECUTABLE_ENV,
    MATRIXMEDIA_PLATFORM_CODES,
    MATRIXMEDIA_TIMEOUT_SECONDS,
    PROJECT_ROOT,
)
from ._errors import MatrixMediaCommandError, PublishAccountGroupError


_LOGIN_SESSIONS: dict[str, dict] = {}


def _matrixmedia_command() -> tuple[list[str], Path]:
    configured = os.getenv(MATRIXMEDIA_EXECUTABLE_ENV, "").strip()
    matrix_dir = Path(os.getenv(MATRIXMEDIA_DIR_ENV, "") or PROJECT_ROOT / "integrations" / "MatrixMedia").resolve()
    if configured:
        executable = Path(configured).expanduser().resolve()
        if not executable.is_file():
            raise MatrixMediaCommandError(
                f"{MATRIXMEDIA_EXECUTABLE_ENV} 指向的文件不存在：{executable}",
                {"fix": "请配置已安装的 MatrixMedia 可执行文件绝对路径"},
            )
        return [str(executable), "cli"], matrix_dir
    electron = matrix_dir / "node_modules" / "electron" / "dist" / "electron.exe"
    built_main = matrix_dir / "dist" / "electron" / "main.js"
    if electron.is_file() and built_main.is_file():
        # 受限环境（沙箱/无 GPU 会话）下 GPU 进程会崩溃退出：--no-sandbox 允许 GPU 进程启动，
        # --disable-gpu 降低对显卡依赖；注意不能加 --in-process-gpu，否则 webview 加载 about:blank 会 ERR_FAILED。
        return [str(electron), "--no-sandbox", "--disable-gpu", ".", "--", "cli"], matrix_dir
    installed = shutil.which("matrixmedia")
    if installed:
        return [installed, "cli"], matrix_dir
    local_app_data = Path(os.getenv("LOCALAPPDATA", ""))
    installed_executable = local_app_data / "Programs" / "matrixmedia" / "matrixmedia.exe"
    if installed_executable.is_file():
        return [str(installed_executable), "cli"], matrix_dir
    raise MatrixMediaCommandError(
        "找不到 MatrixMedia CLI，无法查询本机账号组",
        {
            "fix": f"请设置 {MATRIXMEDIA_EXECUTABLE_ENV}，或安装 matrixmedia 命令",
            "matrixmedia_dir": str(matrix_dir),
        },
    )


def _last_json(text: str):
    lines = [line.strip() for line in str(text or "").splitlines() if line.strip()]
    for line in reversed(lines):
        try:
            return json.loads(line)
        except json.JSONDecodeError:
            continue
    for start in [text.find("["), text.find("{")]:
        if start < 0:
            continue
        try:
            return json.loads(text[start:])
        except json.JSONDecodeError:
            continue
    return None


def _latest_matrixmedia_log() -> Path | None:
    log_dir = Path(os.getenv("APPDATA", "")) / "matrix-video" / "logs"
    if not log_dir.is_dir():
        return None
    files = [item for item in log_dir.glob("*.log") if item.is_file()]
    return max(files, key=lambda item: item.stat().st_mtime) if files else None


def _last_log_json(text: str):
    chunks = []
    current = []
    prefix = re.compile(r"^\[[^\]]+\] \[(?:LOG|INFO|WARN|ERROR|DEBUG)\] ?")
    for line in str(text or "").splitlines():
        if prefix.match(line):
            if current:
                chunks.append("\n".join(current).strip())
            current = [prefix.sub("", line)]
        elif current:
            current.append(line)
    if current:
        chunks.append("\n".join(current).strip())
    for chunk in reversed(chunks):
        try:
            return json.loads(chunk)
        except json.JSONDecodeError:
            continue
    return None


def run_matrixmedia_cli(arguments: list[str]) -> dict | list:
    """调用 MatrixMedia 公开 CLI；不读写其仓库源码。"""
    prefix, cwd = _matrixmedia_command()
    env = dict(os.environ)
    env.pop("ELECTRON_RUN_AS_NODE", None)
    log_path = _latest_matrixmedia_log()
    log_offset = log_path.stat().st_size if log_path else 0
    try:
        result = subprocess.run(
            [*prefix, *arguments],
            cwd=cwd,
            env=env,
            capture_output=True,
            text=True,
            encoding="utf-8",
            errors="replace",
            timeout=MATRIXMEDIA_TIMEOUT_SECONDS,
            check=False,
        )
    except (OSError, subprocess.SubprocessError) as exc:
        raise MatrixMediaCommandError(f"运行 MatrixMedia CLI 失败：{exc}") from exc
    payload = _last_json(result.stdout) or _last_json(result.stderr)
    latest_log = _latest_matrixmedia_log()
    if payload is None and latest_log:
        try:
            with latest_log.open("r", encoding="utf-8", errors="replace") as stream:
                if latest_log == log_path:
                    stream.seek(log_offset)
                payload = _last_log_json(stream.read())
        except OSError:
            payload = None
    if result.returncode != 0:
        message = payload.get("message") if isinstance(payload, dict) else ""
        raise MatrixMediaCommandError(
            f"MatrixMedia CLI 返回失败（退出码 {result.returncode}）：{message or result.stderr[-500:]}",
            {"exit_code": result.returncode},
        )
    if payload is None:
        raise MatrixMediaCommandError("MatrixMedia CLI 未返回可解析的 JSON")
    return payload


def _matrixmedia_account_rows() -> list:
    rows = []
    for group in ("finance", "korean"):
        payload = run_matrixmedia_cli(["accounts", "--json", "--phone", group])
        chunk = payload if isinstance(payload, list) else payload.get("accounts", [])
        if isinstance(chunk, list):
            rows.extend(chunk)
    return rows


def list_matrixmedia_accounts() -> list[dict]:
    rows = _matrixmedia_account_rows()
    accounts = []
    for item in rows:
        if not isinstance(item, dict):
            continue
        raw_platform = str(item.get("pt") or item.get("platform") or "").strip()
        platform = MATRIXMEDIA_CODE_PLATFORMS.get(raw_platform, raw_platform)
        group = str(item.get("phone") or item.get("account_group") or item.get("group") or "").strip()
        if platform not in MATRIXMEDIA_PLATFORM_CODES or not group:
            continue
        if item.get("loggedIn") is False:
            continue
        accounts.append({
            "platform": platform,
            "connector": "matrixmedia",
            "account_id": group,
            "account_ref": group,
            "display_name": str(item.get("name") or item.get("title") or group),
            "login_status": "connected" if item.get("loggedIn") is True else str(item.get("status") or item.get("login_status") or "unknown"),
            "raw": item,
        })
    return accounts


def list_matrixmedia_login_states() -> list[dict]:
    """返回 MatrixMedia 对 Cookie 的实时检查结果，包含已失效账号。"""
    rows = _matrixmedia_account_rows()
    states = []
    for item in rows:
        if not isinstance(item, dict):
            continue
        raw_platform = str(item.get("pt") or item.get("platform") or "").strip()
        platform = MATRIXMEDIA_CODE_PLATFORMS.get(raw_platform, raw_platform)
        account_ref = str(item.get("phone") or item.get("account_group") or item.get("group") or "").strip()
        if platform not in MATRIXMEDIA_PLATFORM_CODES or not account_ref:
            continue
        logged_in = item.get("loggedIn") is True
        states.append({
            "platform": platform,
            "account_ref": account_ref,
            "logged_in": logged_in,
            "reason": str(item.get("reason") or "") if not logged_in else "",
            "expire_at": item.get("expireAt"),
            "login_required": not logged_in,
            "login_tool": "publishing_start_matrixmedia_login" if not logged_in else None,
        })
    return states


def _matrixmedia_login_target(business_line: str, account_group: str, platform: str) -> dict:
    """从数据库账号组解析 MatrixMedia 扫码登录目标，不依赖当前登录态。"""
    database = _database_groups(business_line)
    selected = next((item for item in database if str(item["name"]) == account_group), None)
    if selected is None:
        raise PublishAccountGroupError(
            f"找不到数据库账号组“{account_group}”",
            {"business_line": business_line, "account_group": account_group},
        )
    matches = [
        item for item in selected["members"]
        if str(item.get("platform") or "") == platform
        and str(item.get("connector") or "") == "matrixmedia"
    ]
    if len(matches) != 1:
        raise PublishAccountGroupError(
            f"账号组“{account_group}”没有唯一的 {platform} MatrixMedia 账号",
            {"account_group": account_group, "platform": platform, "matches": len(matches)},
        )
    account_ref = str(matches[0].get("account_ref") or "").strip()
    if not account_ref:
        raise PublishAccountGroupError(
            f"账号组“{account_group}”的 {platform} 账号缺少 account_ref",
            {"account_group": account_group, "platform": platform},
        )
    return {"platform": platform, "account_ref": account_ref}


def _drain_login_stderr(session: dict) -> None:
    stream = session["process"].stderr
    if stream is None:
        return
    for line in stream:
        session["stderr"] = (session["stderr"] + line)[-4000:]


def _login_payload(session: dict) -> dict:
    process = session["process"]
    exit_code = process.poll()
    qr_path = Path(session["qr_path"])
    if exit_code == 0:
        status = "success"
        message = "扫码登录成功，可以重新执行发布预检或发布"
    elif exit_code is not None:
        status = "failed"
        message = session["stderr"].strip()[-800:] or f"MatrixMedia 登录进程退出码 {exit_code}"
    elif qr_path.is_file() and qr_path.stat().st_size >= 80:
        status = "waiting_scan"
        message = "请把二维码图片展示给用户扫码，然后调用 publishing_matrixmedia_login_status"
    else:
        status = "starting"
        message = "正在打开登录页并提取二维码"
    return {
        "status": status,
        "login_id": session["login_id"],
        "business_line": session["business_line"],
        "account_group": session["account_group"],
        "platform": session["platform"],
        "account_ref": session["account_ref"],
        "qr_path": str(qr_path) if qr_path.is_file() else None,
        "message": message,
        "exit_code": exit_code,
    }


def start_matrixmedia_login(
    business_line: str,
    account_group: str,
    platform: str,
    *,
    timeout_seconds: int = 900,
    force: bool = True,
) -> dict:
    """启动 MatrixMedia 扫码登录并等待二维码文件就绪。"""
    normalized = str(platform or "").strip().casefold()
    aliases = {
        "douyin": "douyin", "dy": "douyin",
        "kuaishou": "kuaishou", "ks": "kuaishou",
        "toutiao": "toutiao", "tt": "toutiao",
        "wechat_channels": "wechat_channels", "sph": "wechat_channels",
    }
    normalized = aliases.get(normalized, normalized)
    if normalized not in {"douyin", "kuaishou", "toutiao", "wechat_channels"}:
        raise PublishAccountGroupError("扫码登录只支持抖音、快手、头条和视频号", {"platform": platform})
    target = _matrixmedia_login_target(business_line, account_group, normalized)
    login_id = uuid.uuid4().hex
    qr_path = Path(tempfile.gettempdir()) / f"matrixmedia-login-{login_id}.png"
    prefix, cwd = _matrixmedia_command()
    command = [
        *prefix,
        "login",
        "-p",
        MATRIXMEDIA_PLATFORM_CODES[normalized],
        "--phone",
        target["account_ref"],
        "--save-qr-png",
        str(qr_path),
        "--timeout-sec",
        str(max(30, int(timeout_seconds))),
    ]
    if force:
        command.append("--force")
    env = dict(os.environ)
    env.pop("ELECTRON_RUN_AS_NODE", None)
    try:
        process = subprocess.Popen(
            command,
            cwd=cwd,
            env=env,
            stdout=subprocess.DEVNULL,
            stderr=subprocess.PIPE,
            text=True,
            encoding="utf-8",
            errors="replace",
        )
    except OSError as exc:
        raise MatrixMediaCommandError(
            f"启动 MatrixMedia 扫码登录失败：{exc}",
            {"platform": normalized, "account_ref": target["account_ref"]},
        ) from exc
    session = {
        "login_id": login_id,
        "business_line": business_line,
        "account_group": account_group,
        "platform": normalized,
        "account_ref": target["account_ref"],
        "qr_path": str(qr_path),
        "process": process,
        "stderr": "",
    }
    _LOGIN_SESSIONS[login_id] = session
    threading.Thread(target=_drain_login_stderr, args=(session,), daemon=True).start()
    deadline = time.monotonic() + 90
    while time.monotonic() < deadline:
        payload = _login_payload(session)
        if payload["status"] != "starting":
            return payload
        time.sleep(0.4)
    process.terminate()
    _LOGIN_SESSIONS.pop(login_id, None)
    raise MatrixMediaCommandError("90 秒内没有提取到登录二维码", {"platform": normalized, "account_ref": target["account_ref"]})


def matrixmedia_login_status(login_id: str) -> dict:
    """查询扫码登录结果；等待中继续返回最新二维码路径。"""
    session = _LOGIN_SESSIONS.get(str(login_id or "").strip())
    if session is None:
        raise MatrixMediaCommandError("找不到扫码登录会话，请重新启动登录", {"login_id": login_id})
    payload = _login_payload(session)
    if payload["status"] in {"success", "failed"}:
        _LOGIN_SESSIONS.pop(session["login_id"], None)
    return payload


def _database_groups(business_line: str | None = None) -> list[dict]:
    payload = list_publishing_account_groups(business_line=business_line)
    members_by_group: dict[str, list[dict]] = {}
    for member in payload["members"]:
        members_by_group.setdefault(str(member["group_code"]), []).append(dict(member))
    return [
        {**group, "source": "database", "members": members_by_group.get(str(group["code"]), [])}
        for group in payload["groups"]
    ]


def list_account_groups(business_line: str | None = None) -> dict:
    """返回 D1 账号组，并尽量合并 MatrixMedia 当前已登录账号组。"""
    groups = _database_groups(business_line)
    all_database_names = {str(item["name"]) for item in _database_groups(None)}
    matrix_error = None
    try:
        matrix_accounts = list_matrixmedia_accounts()
        matrix_login_states = list_matrixmedia_login_states()
    except MatrixMediaCommandError as exc:
        matrix_accounts = []
        matrix_login_states = []
        matrix_error = str(exc)
    for group in groups:
        live = [item for item in matrix_accounts if item["account_ref"] == group["name"]]
        group["matrixmedia_accounts"] = live
    for name in sorted({item["account_ref"] for item in matrix_accounts} - all_database_names):
        groups.append({
            "code": f"matrixmedia:{name}",
            "name": name,
            "business_line": None,
            "enabled": 1,
            "source": "matrixmedia",
            "members": [],
            "matrixmedia_accounts": [item for item in matrix_accounts if item["account_ref"] == name],
        })
    return {
        "groups": groups,
        "matrixmedia_login_states": matrix_login_states,
        "matrixmedia_error": matrix_error,
    }


def _official_members(member: dict) -> list[dict]:
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

    if platform == "youtube":
        rows = list_youtube_accounts(account=account_ref)
        return [verified({"display_name": row["channel_title"]}, row["channel_id"], row["channel_id"]) for row in rows]
    if platform == "tiktok":
        rows = list_tiktok_accounts(account=None if account_ref == "configured" else account_ref)
        return [
            verified(
                {"account_ref": row["account"], "display_name": row["account_title"]},
                row["account_id"], row["platform_account_id"],
            )
            for row in rows
        ]
    if platform == "instagram":
        rows = list_instagram_accounts()
        return [verified({"display_name": row["account_title"]}, row["user_id"], row["platform_account_id"]) for row in rows]
    if platform == "facebook":
        rows = list_facebook_accounts()
        return [verified({"display_name": row["page_name"]}, row["page_id"], row["platform_account_id"]) for row in rows]
    return [{**member, "account_id": account_ref, "platform_account_id": stored_platform_account_id, "display_name": display_name}]


def resolve_account_group(account_group: str, business_line: str, platforms: list[str]) -> list[dict]:
    requested = set(platforms)
    database = _database_groups(business_line)
    selected = next((item for item in database if str(item["name"]) == account_group), None)
    known_group = next(
        (item for item in _database_groups(None) if str(item["name"]) == account_group),
        None,
    )
    if selected is None and known_group is not None:
        raise PublishAccountGroupError(
            f"账号组“{account_group}”属于 {known_group['business_line']}，不能用于 {business_line}",
            {"account_group": account_group, "expected_business_line": known_group["business_line"]},
        )
    try:
        live_matrix = list_matrixmedia_accounts()
    except MatrixMediaCommandError:
        live_matrix = []
    if selected:
        routes = []
        for member in selected["members"]:
            if member["platform"] not in requested:
                continue
            if member["connector"] == "matrixmedia":
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
            f"找不到数据库账号组“{account_group}”；未入库的 MatrixMedia 登录态不能直接用于发布",
            {"account_group": account_group},
        )
    missing = sorted(requested - {str(item["platform"]) for item in routes})
    if missing:
        login_required = [
            {
                "platform": str(member["platform"]),
                "account_ref": str(member.get("account_ref") or ""),
                "login_tool": "publishing_start_matrixmedia_login",
            }
            for member in (selected.get("members") or [])
            if str(member.get("platform") or "") in missing
            and str(member.get("connector") or "") == "matrixmedia"
        ]
        raise PublishAccountGroupError(
            f"账号组“{account_group}”缺少这些平台的可用账号：{', '.join(missing)}",
            {
                "account_group": account_group,
                "missing_platforms": missing,
                "login_required": login_required,
                "next_step": "对 login_required 逐项调用 publishing_start_matrixmedia_login，并把 qr_path 图片展示给用户",
            },
        )
    return routes
