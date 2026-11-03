"""合并数据库账号组、官方账号和 media-publisher 本机账号。"""

from __future__ import annotations

import json
import os
import re
import shutil
import subprocess
import sys
import tempfile
import threading
import time
import uuid
from pathlib import Path

from core.tools.media_records import list_publishing_account_groups

from ._constants import (
    MEDIA_PUBLISHER_CODE_PLATFORMS,
    MEDIA_PUBLISHER_PLATFORM_CODES,
    MEDIA_PUBLISHER_EXECUTABLE_ENV,
    MEDIA_PUBLISHER_TIMEOUT_SECONDS,
    media_publisher_executable,
    media_publisher_root,
)
from ._errors import MediaPublisherCommandError, PublishAccountGroupError
from .content import normalize_platforms


_LOGIN_SESSIONS: dict[str, dict] = {}
_ACCOUNT_ROWS_CACHE: dict[tuple, tuple[float, list]] = {}
_ACCOUNT_ROWS_LOCK = threading.Lock()


def _publisher_command() -> tuple[list[str], Path]:
    configured = media_publisher_executable()
    matrix_dir = media_publisher_root()
    if configured:
        executable = Path(configured).expanduser().resolve()
        if not executable.is_file():
            raise MediaPublisherCommandError(
                f"{MEDIA_PUBLISHER_EXECUTABLE_ENV} 指向的文件不存在：{executable}",
                {"fix": "请配置已安装的 media-publisher 可执行文件绝对路径"},
            )
        return [str(executable), "cli"], matrix_dir
    electron = matrix_dir / "node_modules" / "electron" / "dist" / "electron.exe"
    built_main = matrix_dir / "dist" / "electron" / "main.js"
    if electron.is_file() and built_main.is_file():
        # 受限环境（沙箱/无 GPU 会话）下 GPU 进程会崩溃退出：--no-sandbox 允许 GPU 进程启动，
        # --disable-gpu 降低对显卡依赖；注意不能加 --in-process-gpu，否则 webview 加载 about:blank 会 ERR_FAILED。
        return [str(electron), "--no-sandbox", "--disable-gpu", ".", "--", "cli"], matrix_dir
    installed = shutil.which("media-publisher")
    if installed:
        return [installed, "cli"], matrix_dir
    local_app_data = Path(os.getenv("LOCALAPPDATA", ""))
    installed_executable = local_app_data / "Programs" / "media-publisher" / "media-publisher.exe"
    if installed_executable.is_file():
        return [str(installed_executable), "cli"], matrix_dir
    raise MediaPublisherCommandError(
        "找不到 media-publisher CLI，无法查询本机账号组",
        {
            "fix": f"请设置 {MEDIA_PUBLISHER_EXECUTABLE_ENV}，或安装 media-publisher 命令",
            "media_publisher_dir": str(matrix_dir),
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


def _latest_publisher_log() -> Path | None:
    log_dir = Path(os.getenv("APPDATA", "")) / "media-publisher" / "logs"
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


def _flag_value(arguments: list[str], *flags: str) -> str:
    for index, item in enumerate(arguments):
        if item in flags and index + 1 < len(arguments):
            return str(arguments[index + 1] or "").strip()
    return ""


def _is_official_cli(arguments: list[str]) -> bool:
    if not arguments:
        return False
    if arguments[0] == "accounts" and "--official" in arguments:
        return True
    if arguments[0] != "publish":
        return False
    platform = _flag_value(arguments, "-p", "--platform").casefold()
    return platform in {"youtube", "yt", "ytb", "tiktok", "tk", "instagram", "ig", "ins", "facebook", "fb"}


def _run_official_python(arguments: list[str]) -> dict | list:
    """YouTube 与 Zernio 走矩媒里的 Python 包，GitHub Runner 不依赖本机 Electron。"""
    matrix_dir = media_publisher_root()
    if arguments[0] == "accounts":
        cli_args = ["accounts", "--group", _flag_value(arguments, "--phone", "--group")]
    else:
        cli_args = arguments
    env = dict(os.environ)
    python_dir = str(matrix_dir / "python")
    current_path = env.get("PYTHONPATH", "")
    env["PYTHONPATH"] = python_dir if not current_path else python_dir + os.pathsep + current_path
    env["PYTHONUTF8"] = "1"
    try:
        result = subprocess.run(
            [sys.executable, "-m", "platform_api.cli", *cli_args],
            cwd=matrix_dir,
            env=env,
            capture_output=True,
            text=True,
            encoding="utf-8",
            errors="replace",
            timeout=MEDIA_PUBLISHER_TIMEOUT_SECONDS,
            check=False,
        )
    except (OSError, subprocess.SubprocessError) as exc:
        raise MediaPublisherCommandError(f"运行矩媒官方发布失败：{exc}") from exc
    payload = _last_json(result.stdout)
    if payload is None:
        payload = _last_json(result.stderr)
    if result.returncode != 0:
        message = ""
        if isinstance(payload, dict):
            message = str(payload.get("message") or payload.get("error") or "")
        raise MediaPublisherCommandError(
            f"矩媒官方发布失败（退出码 {result.returncode}）：{message or result.stderr[-500:]}",
            {"exit_code": result.returncode},
        )
    if payload is None:
        raise MediaPublisherCommandError("矩媒官方发布未返回可解析的 JSON")
    return payload


def run_publisher_cli(arguments: list[str]) -> dict | list:
    """扫码平台调用 media-publisher Electron；YouTube 与 Zernio 调用官方发布包。"""
    if _is_official_cli(arguments):
        return _run_official_python(arguments)
    prefix, cwd = _publisher_command()
    env = dict(os.environ)
    env.pop("ELECTRON_RUN_AS_NODE", None)
    env["MEDIA_PUBLISHER_PARENT_PID"] = str(os.getpid())
    log_path = _latest_publisher_log()
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
            timeout=MEDIA_PUBLISHER_TIMEOUT_SECONDS,
            check=False,
        )
    except (OSError, subprocess.SubprocessError) as exc:
        raise MediaPublisherCommandError(f"运行 media-publisher CLI 失败：{exc}") from exc
    payload = _last_json(result.stdout)
    if payload is None:
        payload = _last_json(result.stderr)
    latest_log = _latest_publisher_log()
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
        raise MediaPublisherCommandError(
            f"media-publisher CLI 返回失败（退出码 {result.returncode}）：{message or result.stderr[-500:]}",
            {"exit_code": result.returncode},
        )
    if payload is None:
        raise MediaPublisherCommandError("media-publisher CLI 未返回可解析的 JSON")
    return payload


def _clear_account_rows_cache(account_ref: str) -> None:
    for key in list(_ACCOUNT_ROWS_CACHE):
        if key[0] == account_ref:
            _ACCOUNT_ROWS_CACHE.pop(key, None)


def _publisher_account_rows(account_refs: list[str] | None = None, *, platforms: list[str] | None = None,
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
    rows = _publisher_account_rows(account_refs) if rows is None else rows
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
    rows = _publisher_account_rows() if rows is None else rows
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


def _publisher_login_target(business_line: str, account_group: str, platform: str) -> dict:
    """从数据库账号组解析 media-publisher 扫码登录目标，不依赖当前登录态。"""
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
        and str(item.get("connector") or "") == "media-publisher"
    ]
    if len(matches) != 1:
        raise PublishAccountGroupError(
            f"账号组“{account_group}”没有唯一的 {platform} media-publisher 账号",
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
        message = session["stderr"].strip()[-800:] or f"media-publisher 登录进程退出码 {exit_code}"
    elif qr_path.is_file() and qr_path.stat().st_size >= 80:
        status = "waiting_scan"
        message = "请把二维码图片展示给用户扫码，然后调用 publishing_login_status"
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


def start_publisher_login(
    business_line: str,
    account_group: str,
    platform: str,
    *,
    timeout_seconds: int = 900,
    force: bool = True,
) -> dict:
    """启动 media-publisher 扫码登录并等待二维码文件就绪。"""
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
    target = _publisher_login_target(business_line, account_group, normalized)
    _clear_account_rows_cache(target["account_ref"])
    login_id = uuid.uuid4().hex
    qr_path = Path(tempfile.gettempdir()) / f"media-publisher-login-{login_id}.png"
    prefix, cwd = _publisher_command()
    command = [
        *prefix,
        "login",
        "-p",
        MEDIA_PUBLISHER_PLATFORM_CODES[normalized],
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
    env["MEDIA_PUBLISHER_PARENT_PID"] = str(os.getpid())
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
        raise MediaPublisherCommandError(
            f"启动 media-publisher 扫码登录失败：{exc}",
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
    if os.name == "nt":
        subprocess.run(["taskkill", "/PID", str(process.pid), "/T", "/F"], capture_output=True, creationflags=subprocess.CREATE_NO_WINDOW)
    else:
        process.terminate()
    process.wait(timeout=10)
    _LOGIN_SESSIONS.pop(login_id, None)
    raise MediaPublisherCommandError("90 秒内没有提取到登录二维码", {"platform": normalized, "account_ref": target["account_ref"]})


def publisher_login_status(login_id: str) -> dict:
    """查询扫码登录结果；等待中继续返回最新二维码路径。"""
    session = _LOGIN_SESSIONS.get(str(login_id or "").strip())
    if session is None:
        raise MediaPublisherCommandError("找不到扫码登录会话，请重新启动登录", {"login_id": login_id})
    payload = _login_payload(session)
    if payload["status"] in {"success", "failed"}:
        _clear_account_rows_cache(session["account_ref"])
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


def list_account_groups(business_line: str | None = None, account_group: str | None = None,
                        platforms: list[str] | None = None) -> dict:
    """只读取并筛选数据库账号组配置，不打开浏览器或检查授权。"""
    database = _database_groups(None)
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
                    detected = _publisher_account_rows([member["account_ref"]], platforms=[member["platform"]], refresh=True)
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
    with _ACCOUNT_ROWS_LOCK:
        for account_ref in {row["phone"] for row in rows}:
            selected_rows = [row for row in rows if row["phone"] == account_ref]
            selected_platforms = tuple(sorted({MEDIA_PUBLISHER_CODE_PLATFORMS.get(row["pt"], row["pt"]) for row in selected_rows}))
            _ACCOUNT_ROWS_CACHE[(account_ref, selected_platforms)] = (time.monotonic(), selected_rows)
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
    database = _database_groups(None)
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
        rows.extend(_publisher_account_rows([account_ref], platforms=browser_platforms))
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
            "screenshot_path": item.get("screenshotPath"),
            "current_url": item.get("currentUrl"),
                "account_states": account_states,
                "inspection_errors": [state for state in account_states if state["status"] == "error"] + unavailable,
                "next_step": "仅对 login_required 调用扫码登录；检测失败先处理页面或网络问题，再重新预检",
            },
        )
    return routes


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
