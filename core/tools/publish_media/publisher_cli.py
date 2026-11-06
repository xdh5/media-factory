"""定位发布器进程、区分官方与浏览器命令并解析结果。"""

from __future__ import annotations

import json
import os
import re
import shutil
import subprocess
import sys
from pathlib import Path


from ._constants import (
    MEDIA_PUBLISHER_EXECUTABLE_ENV,
    MEDIA_PUBLISHER_TIMEOUT_SECONDS,
    media_publisher_executable,
    media_publisher_root,
)
from ._errors import MediaPublisherCommandError


def resolve_publisher_command() -> tuple[list[str], Path]:
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
    prefix, cwd = resolve_publisher_command()
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
