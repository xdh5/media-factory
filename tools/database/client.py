"""公共数据 API 请求与共享记录读写。"""

from __future__ import annotations

import json
import os
import subprocess
import time
from urllib.error import HTTPError, URLError
from urllib.parse import urlencode
from urllib.request import Request, urlopen

from dotenv import load_dotenv

from ._constants import (
    CLOUDFLARE_DATA_API_TOKEN_ENV,
    CLOUDFLARE_DATA_API_URL_ENV,
    CURL_MAX_ATTEMPTS,
    CURL_RETRY_DELAY_SECONDS,
    DEFAULT_CURL_MAX_TIME_SECONDS,
    DEFAULT_REQUEST_TIMEOUT_SECONDS,
    MAX_RESPONSE_BYTES,
)
from ._errors import (
    DatabaseConfigurationError,
    DatabaseConflictError,
    DatabaseRequestError,
)

load_dotenv()


def _configuration() -> tuple[str, str]:
    base_url = os.getenv(CLOUDFLARE_DATA_API_URL_ENV, "").strip().rstrip("/")
    token = os.getenv(CLOUDFLARE_DATA_API_TOKEN_ENV, "").strip()
    missing = []
    if not base_url:
        missing.append(CLOUDFLARE_DATA_API_URL_ENV)
    if not token:
        missing.append(CLOUDFLARE_DATA_API_TOKEN_ENV)
    if missing:
        raise DatabaseConfigurationError(
            f"媒体生产记录未配置：缺少 {', '.join(missing)}",
            {"missing_environment_variables": missing},
        )
    if not base_url.startswith("https://"):
        raise DatabaseConfigurationError(
            f"{CLOUDFLARE_DATA_API_URL_ENV} 必须使用 https:// 地址",
            {"environment_variable": CLOUDFLARE_DATA_API_URL_ENV},
        )
    return base_url, token


def _decode_response(raw: bytes, *, status: int) -> dict | list:
    if len(raw) > MAX_RESPONSE_BYTES:
        raise DatabaseRequestError(
            "媒体生产记录响应过大，已停止读取",
            {"status": status, "maximum_bytes": MAX_RESPONSE_BYTES},
        )
    try:
        payload = json.loads(raw.decode("utf-8"))
    except (UnicodeDecodeError, json.JSONDecodeError) as exc:
        raise DatabaseRequestError(
            "媒体生产记录返回了无法解析的 JSON",
            {"status": status},
        ) from exc
    if not isinstance(payload, (dict, list)):
        raise DatabaseRequestError(
            "媒体生产记录响应必须是 JSON 对象或数组",
            {"status": status},
        )
    return payload


def _remote_error(payload: object, *, status: int) -> tuple[str, str, dict]:
    error = payload.get("error") if isinstance(payload, dict) else None
    if not isinstance(error, dict):
        return "REMOTE_ERROR", f"媒体生产记录请求失败（HTTP {status}）", {"status": status}
    code = str(error.get("code") or "REMOTE_ERROR")
    message = str(error.get("message") or f"媒体生产记录请求失败（HTTP {status}）")
    details = error.get("details") if isinstance(error.get("details"), dict) else {}
    return code, message, {**details, "status": status}


def _request_with_curl(method: str, url: str, token: str, data: bytes | None) -> tuple[int, bytes]:
    """优先使用系统 curl，规避本机 Python TLS 兼容性问题。"""
    command = [
        "curl.exe" if os.name == "nt" else "curl",
        "--silent",
        "--show-error",
        "--http1.1",
        "--tlsv1.2",
        "--connect-timeout",
        "10",
        "--retry",
        "2",
        "--retry-all-errors",
        "--retry-delay",
        str(CURL_RETRY_DELAY_SECONDS),
        "--request",
        method,
        "--header",
        f"Authorization: Bearer {token}",
        "--header",
        "Accept: application/json",
        "--header",
        "Content-Type: application/json; charset=utf-8",
        "--header",
        "User-Agent: media-factory/1.0",
        "--max-time",
        str(DEFAULT_CURL_MAX_TIME_SECONDS),
        "--output",
        "-",
        "--write-out",
        "\n%{http_code}",
    ]
    if data is not None:
        command.extend(["--data-binary", data.decode("utf-8")])
    command.append(url)
    last_detail = ""
    for attempt in range(CURL_MAX_ATTEMPTS):
        completed = subprocess.run(
            command,
            capture_output=True,
            check=False,
            timeout=DEFAULT_CURL_MAX_TIME_SECONDS + 5,
        )
        raw, separator, status_text = completed.stdout.rpartition(b"\n")
        if separator and status_text.isdigit() and status_text != b"000":
            return int(status_text), raw
        last_detail = completed.stderr.decode("utf-8", errors="replace").strip() or str(completed.returncode)
        if attempt < CURL_MAX_ATTEMPTS - 1:
            time.sleep(CURL_RETRY_DELAY_SECONDS * (attempt + 1))
    raise OSError(f"系统 curl 重试 {CURL_MAX_ATTEMPTS} 次后仍未取得 HTTP 响应：{last_detail}")


def _request(method: str, path: str, *, query: dict | None = None, body: dict | None = None) -> dict | list:
    base_url, token = _configuration()
    url = f"{base_url}{path}"
    if query:
        url = f"{url}?{urlencode(query)}"
    data = None if body is None else json.dumps(body, ensure_ascii=False).encode("utf-8")
    try:
        status, raw = _request_with_curl(method, url, token, data)
        payload = _decode_response(raw, status=status)
        if 200 <= status < 300:
            return payload
        code, message, details = _remote_error(payload, status=status)
        if status == 409:
            raise DatabaseConflictError(message, details, remote_code=code)
        raise DatabaseRequestError(message, {**details, "remote_code": code})
    except (DatabaseConflictError, DatabaseRequestError):
        raise
    except (FileNotFoundError, OSError, subprocess.TimeoutExpired):
        pass

    request = Request(
        url,
        data=data,
        method=method,
        headers={
            "Authorization": f"Bearer {token}",
            "Accept": "application/json",
            "Content-Type": "application/json; charset=utf-8",
            "User-Agent": "media-factory/1.0",
        },
    )
    try:
        with urlopen(request, timeout=DEFAULT_REQUEST_TIMEOUT_SECONDS) as response:
            payload = _decode_response(response.read(MAX_RESPONSE_BYTES + 1), status=response.status)
    except HTTPError as exc:
        raw = exc.read(MAX_RESPONSE_BYTES + 1)
        try:
            payload = _decode_response(raw, status=exc.code)
        except DatabaseRequestError:
            payload = {}
        code, message, details = _remote_error(payload, status=exc.code)
        if exc.code == 409:
            raise DatabaseConflictError(message, details, remote_code=code) from exc
        raise DatabaseRequestError(message, {**details, "remote_code": code}) from exc
    except (URLError, TimeoutError, OSError) as exc:
        raise DatabaseRequestError(
            f"无法连接媒体生产记录：{exc}",
            {"url": url},
        ) from exc
    return payload
