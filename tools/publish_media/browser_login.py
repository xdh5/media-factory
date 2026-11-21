"""启动浏览器扫码进程，管理二维码及登录结果。"""

from __future__ import annotations

import os
import subprocess
import tempfile
import threading
import time
import uuid
from pathlib import Path


from ._constants import (
    MEDIA_PUBLISHER_PLATFORM_CODES,
)
from ._errors import MediaPublisherCommandError, PublishAccountGroupError
from .accounts import load_database_groups
from .browser_accounts import clear_account_rows_cache
from .publisher_cli import resolve_publisher_command


_LOGIN_SESSIONS: dict[str, dict] = {}


def _publisher_login_target(business_line: str, account_group: str, platform: str) -> dict:
    """从数据库账号组解析 media-publisher 扫码登录目标，不依赖当前登录态。"""
    database = load_database_groups(business_line)
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
    clear_account_rows_cache(target["account_ref"])
    login_id = uuid.uuid4().hex
    qr_path = Path(tempfile.gettempdir()) / f"media-publisher-login-{login_id}.png"
    prefix, cwd = resolve_publisher_command()
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
        clear_account_rows_cache(session["account_ref"])
        _LOGIN_SESSIONS.pop(session["login_id"], None)
    return payload
