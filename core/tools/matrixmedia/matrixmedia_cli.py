"""仅通过已安装的 MatrixMedia 可执行文件调用 CLI，不引入 GUI 源码。"""

from __future__ import annotations

import json
import os
import re
import shutil
import subprocess
from pathlib import Path

from ._constants import (
    DEFAULT_MATRIXMEDIA_EXECUTABLE,
    EXIT_CODE_MESSAGES,
    HISTORY_STATUSES,
    LOGIN_PLATFORMS,
    LOGIN_TIMEOUT_SECONDS,
    MATRIXMEDIA_EXECUTABLE_ENV,
    MATRIXMEDIA_RUNTIME_LAYOUTS,
    PUBLISH_PLATFORMS,
    PUBLISH_TIMEOUT_SECONDS,
    QUERY_PLATFORMS,
    QUERY_TIMEOUT_SECONDS,
)
from ._errors import (
    CLIExecutableNotFoundError,
    CLIExecutionError,
    CLIOutputError,
    InvalidParameterError,
)

__all__ = ["publish_video", "list_accounts", "list_history", "login_account"]


def _text(value: str | None, parameter: str, *, required: bool = False) -> str | None:
    if value is None and not required:
        return None
    if not isinstance(value, str) or not value.strip():
        raise InvalidParameterError(parameter, f"{parameter} 必须是非空字符串")
    return value.strip()


def _account_args(phone: str | None, partition: str | None) -> list[str]:
    if bool(phone) == bool(partition):
        raise InvalidParameterError("phone/partition", "phone 和 partition 必须且只能传入一个")
    return ["--phone", _text(phone, "phone", required=True)] if phone else [
        "--partition", _text(partition, "partition", required=True),
    ]


def _command_prefix() -> list[str]:
    configured = os.getenv(MATRIXMEDIA_EXECUTABLE_ENV, DEFAULT_MATRIXMEDIA_EXECUTABLE).strip()
    if not configured:
        configured = DEFAULT_MATRIXMEDIA_EXECUTABLE
    path = Path(configured).expanduser()
    if path.is_absolute() or path.parent != Path("."):
        resolved = path.resolve()
        if resolved.is_dir():
            runtime = next(
                (
                    (resolved / entry, resolved / executable)
                    for entry, executable in MATRIXMEDIA_RUNTIME_LAYOUTS
                    if (resolved / entry).is_file() and (resolved / executable).is_file()
                ),
                None,
            )
            if runtime is None:
                raise CLIExecutableNotFoundError(
                    f"MatrixMedia 项目目录缺少已构建入口或 Electron 可执行文件：{resolved}",
                    {
                        "environment_variable": MATRIXMEDIA_EXECUTABLE_ENV,
                        "configured_path": str(resolved),
                        "supported_layouts": MATRIXMEDIA_RUNTIME_LAYOUTS,
                        "fix": "请先构建 MatrixMedia，或改填正式安装后的 matrixmedia 可执行文件",
                    },
                )
            _, executable = runtime
            return [
                str(executable),
                str(resolved),
            ]
        if not resolved.is_file():
            raise CLIExecutableNotFoundError(
                f"MatrixMedia CLI 不存在：{resolved}",
                {"environment_variable": MATRIXMEDIA_EXECUTABLE_ENV, "configured_path": str(resolved)},
            )
        return [str(resolved)]
    executable = shutil.which(configured)
    if not executable:
        raise CLIExecutableNotFoundError(
            f"未找到 MatrixMedia CLI 命令 '{configured}'，请安装后加入 PATH，"
            f"或通过 {MATRIXMEDIA_EXECUTABLE_ENV} 指定可执行文件绝对路径",
            {"environment_variable": MATRIXMEDIA_EXECUTABLE_ENV, "configured_command": configured},
        )
    return [executable]


def _run(arguments: list[str], *, timeout: int, interactive: bool = False) -> dict:
    command = [*_command_prefix(), "cli", *arguments]
    environment = os.environ.copy()
    environment.pop("ELECTRON_RUN_AS_NODE", None)
    try:
        completed = subprocess.run(
            command,
            check=False,
            capture_output=not interactive,
            text=True,
            encoding="utf-8",
            errors="replace",
            timeout=timeout,
            env=environment,
        )
    except subprocess.TimeoutExpired as exc:
        raise CLIExecutionError(
            f"MatrixMedia CLI 执行超过 {timeout} 秒，已终止等待",
            {"command": command, "timeout_seconds": timeout},
        ) from exc
    except OSError as exc:
        raise CLIExecutionError(f"无法启动 MatrixMedia CLI：{exc}", {"command": command}) from exc
    stdout = completed.stdout or ""
    stderr = completed.stderr or ""
    result = {
        "success": completed.returncode == 0,
        "exit_code": completed.returncode,
        "command": command,
        "stdout": stdout.strip()[-10000:],
        "stderr": stderr.strip()[-10000:],
    }
    if completed.returncode != 0:
        message = EXIT_CODE_MESSAGES.get(completed.returncode, "MatrixMedia CLI 执行失败")
        detail = result["stderr"] or result["stdout"]
        raise CLIExecutionError(
            f"{message}（退出码 {completed.returncode}）：{detail or 'CLI 没有返回错误详情'}",
            result,
        )
    return result


def _run_json(arguments: list[str], *, timeout: int = QUERY_TIMEOUT_SECONDS) -> object:
    result = _run([*arguments, "--json"], timeout=timeout)
    try:
        return json.loads(result["stdout"])
    except json.JSONDecodeError:
        # MatrixMedia 0.11.0 的开发目录入口会把启动日志写到 stdout，
        # 机器可读结果仍是其中一行完整 JSON。
        for line in reversed(result["stdout"].splitlines()):
            candidate = line.strip()
            if not candidate:
                continue
            try:
                return json.loads(candidate)
            except json.JSONDecodeError:
                continue
        raise CLIOutputError(
            "MatrixMedia CLI --json 输出中没有找到合法 JSON，请确认当前版本支持机器可读输出",
            {"command": result["command"], "stdout": result["stdout"], "stderr": result["stderr"]},
        )


def publish_video(
    platform: str,
    video_path: str | Path,
    title: str,
    *,
    phone: str | None = None,
    partition: str | None = None,
    short_title: str | None = None,
    tags: list[str] | None = None,
    task_name: str | None = None,
    address: str | None = None,
    publish_at: str | None = None,
    draft: bool = False,
    sph_product_id: str | None = None,
) -> dict:
    """调用 `matrixmedia cli publish` 发布一个本地视频。"""
    if platform not in PUBLISH_PLATFORMS:
        raise InvalidParameterError("platform", f"platform 必须从 {PUBLISH_PLATFORMS} 中选择")
    video = Path(video_path).resolve()
    if not video.is_file():
        raise InvalidParameterError("video_path", f"视频文件不存在：{video}")
    normalized_title = _text(title, "title", required=True)
    if not isinstance(draft, bool):
        raise InvalidParameterError("draft", "draft 必须是布尔值")
    if publish_at and not re.fullmatch(r"\d{4}-\d{2}-\d{2} \d{2}:\d{2}:\d{2}", publish_at):
        raise InvalidParameterError("publish_at", "publish_at 必须使用 YYYY-MM-DD HH:mm:ss 格式")
    if tags is not None:
        if not isinstance(tags, list) or len(tags) > 4 or any(not isinstance(tag, str) or not tag.strip() for tag in tags):
            raise InvalidParameterError("tags", "tags 必须是最多包含 4 个非空字符串的列表")
    arguments = ["publish", "-p", platform, "-f", str(video), "-t", normalized_title]
    arguments.extend(_account_args(phone, partition))
    optional_values = [
        ("--bt2", short_title),
        ("--tags", " ".join(tag.strip() for tag in tags) if tags else None),
        ("--name", task_name),
        ("--address", address),
        ("--publish-at", publish_at),
        ("--sph-product-id", sph_product_id),
    ]
    for flag, value in optional_values:
        if value is not None and str(value).strip():
            arguments.extend([flag, str(value).strip()])
    if draft:
        arguments.append("--draft")
    return _run(arguments, timeout=PUBLISH_TIMEOUT_SECONDS)


def list_accounts(
    platform: str | None = None,
    phone: str | None = None,
    logged_in: bool | None = None,
) -> object:
    """调用 `matrixmedia cli accounts --json` 查询账号登录态。"""
    arguments = ["accounts"]
    if platform is not None:
        if platform not in QUERY_PLATFORMS:
            raise InvalidParameterError("platform", f"platform 必须从 {QUERY_PLATFORMS} 中选择")
        arguments.extend(["-p", platform])
    if phone is not None:
        arguments.extend(["--phone", _text(phone, "phone", required=True)])
    if logged_in is not None:
        if not isinstance(logged_in, bool):
            raise InvalidParameterError("logged_in", "logged_in 必须是布尔值或不传")
        arguments.append("--logged-in" if logged_in else "--logged-out")
    return _run_json(arguments)


def list_history(
    platform: str | None = None,
    phone: str | None = None,
    status: str | None = None,
    *,
    days: int = 7,
    limit: int = 50,
    since: str | None = None,
    until: str | None = None,
) -> object:
    """调用 `matrixmedia cli history --json` 查询发布历史。"""
    if isinstance(days, bool) or not isinstance(days, int) or days < 1:
        raise InvalidParameterError("days", "days 必须是正整数")
    if isinstance(limit, bool) or not isinstance(limit, int) or limit < 1:
        raise InvalidParameterError("limit", "limit 必须是正整数")
    arguments = ["history", "-d", str(days), "-n", str(limit)]
    if platform is not None:
        if platform not in PUBLISH_PLATFORMS:
            raise InvalidParameterError("platform", f"platform 必须从 {PUBLISH_PLATFORMS} 中选择")
        arguments.extend(["-p", platform])
    if phone is not None:
        arguments.extend(["--phone", _text(phone, "phone", required=True)])
    if status is not None:
        if status not in HISTORY_STATUSES:
            raise InvalidParameterError("status", f"status 必须从 {HISTORY_STATUSES} 中选择")
        arguments.extend(["-s", status])
    for flag, value in (("--since", since), ("--until", until)):
        if value is not None:
            if not re.fullmatch(r"\d{4}-\d{2}-\d{2}", value):
                raise InvalidParameterError(flag[2:], f"{flag} 必须使用 YYYY-MM-DD 格式")
            arguments.extend([flag, value])
    return _run_json(arguments)


def login_account(
    platform: str,
    *,
    phone: str | None = None,
    partition: str | None = None,
    timeout_seconds: int = LOGIN_TIMEOUT_SECONDS,
    save_qr_png: str | Path | None = None,
    puppeteer_headless: bool = False,
    force: bool = False,
) -> dict:
    """调用 CLI 扫码登录；不启动本项目 GUI，二维码输出到当前终端或指定 PNG。"""
    if platform not in LOGIN_PLATFORMS:
        raise InvalidParameterError("platform", f"CLI 登录只支持 {LOGIN_PLATFORMS}")
    if isinstance(timeout_seconds, bool) or not isinstance(timeout_seconds, int) or timeout_seconds < 30:
        raise InvalidParameterError("timeout_seconds", "timeout_seconds 必须是不小于 30 的整数")
    if platform == "sph" and puppeteer_headless:
        raise InvalidParameterError("puppeteer_headless", "视频号 CLI 不支持 puppeteer_headless")
    arguments = ["login", "-p", platform, *_account_args(phone, partition), "--timeout-sec", str(timeout_seconds)]
    if save_qr_png is not None:
        qr_path = Path(save_qr_png).resolve()
        qr_path.parent.mkdir(parents=True, exist_ok=True)
        arguments.extend(["--save-qr-png", str(qr_path)])
    if puppeteer_headless:
        arguments.append("--puppeteer-headless")
    if force:
        arguments.append("--force")
    result = _run(arguments, timeout=timeout_seconds + 30, interactive=True)
    from .account_groups import register_account

    register_account(platform, phone=phone, partition=partition)
    return result
