"""通过鉴权 Worker API 访问 Cloudflare D1。"""

from __future__ import annotations

import json
import os
from urllib.error import HTTPError, URLError
from urllib.parse import urlencode
from urllib.request import Request, urlopen

from dotenv import load_dotenv

from ._constants import (
    CLOUDFLARE_DATA_API_TOKEN_ENV,
    CLOUDFLARE_DATA_API_URL_ENV,
    DEFAULT_REQUEST_TIMEOUT_SECONDS,
    MAX_RESPONSE_BYTES,
)
from ._errors import (
    CloudflareDataConfigurationError,
    CloudflareDataConflictError,
    CloudflareDataRequestError,
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
        raise CloudflareDataConfigurationError(
            f"Cloudflare 数据服务未配置：缺少 {', '.join(missing)}",
            {"missing_environment_variables": missing},
        )
    if not base_url.startswith("https://"):
        raise CloudflareDataConfigurationError(
            f"{CLOUDFLARE_DATA_API_URL_ENV} 必须使用 https:// 地址",
            {"environment_variable": CLOUDFLARE_DATA_API_URL_ENV},
        )
    return base_url, token


def _decode_response(raw: bytes, *, status: int) -> dict | list:
    if len(raw) > MAX_RESPONSE_BYTES:
        raise CloudflareDataRequestError(
            "Cloudflare 数据服务响应过大，已停止读取",
            {"status": status, "maximum_bytes": MAX_RESPONSE_BYTES},
        )
    try:
        payload = json.loads(raw.decode("utf-8"))
    except (UnicodeDecodeError, json.JSONDecodeError) as exc:
        raise CloudflareDataRequestError(
            "Cloudflare 数据服务返回了无法解析的 JSON",
            {"status": status},
        ) from exc
    if not isinstance(payload, (dict, list)):
        raise CloudflareDataRequestError(
            "Cloudflare 数据服务响应必须是 JSON 对象或数组",
            {"status": status},
        )
    return payload


def _remote_error(payload: object, *, status: int) -> tuple[str, str, dict]:
    error = payload.get("error") if isinstance(payload, dict) else None
    if not isinstance(error, dict):
        return "REMOTE_ERROR", f"Cloudflare 数据服务请求失败（HTTP {status}）", {"status": status}
    code = str(error.get("code") or "REMOTE_ERROR")
    message = str(error.get("message") or f"Cloudflare 数据服务请求失败（HTTP {status}）")
    details = error.get("details") if isinstance(error.get("details"), dict) else {}
    return code, message, {**details, "status": status}


def _request(method: str, path: str, *, query: dict | None = None, body: dict | None = None) -> dict | list:
    base_url, token = _configuration()
    url = f"{base_url}{path}"
    if query:
        url = f"{url}?{urlencode(query)}"
    data = None if body is None else json.dumps(body, ensure_ascii=False).encode("utf-8")
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
        except CloudflareDataRequestError:
            payload = {}
        code, message, details = _remote_error(payload, status=exc.code)
        if exc.code == 409:
            raise CloudflareDataConflictError(message, details, remote_code=code) from exc
        raise CloudflareDataRequestError(message, {**details, "remote_code": code}) from exc
    except (URLError, TimeoutError, OSError) as exc:
        raise CloudflareDataRequestError(
            f"无法连接 Cloudflare 数据服务：{exc}",
            {"url": url},
        ) from exc
    return payload


def list_topics(workflow: str, days: int) -> list[dict]:
    payload = _request("GET", "/v1/topics", query={"workflow": workflow, "days": days})
    if not isinstance(payload, dict) or not isinstance(payload.get("records"), list):
        raise CloudflareDataRequestError("Cloudflare 话题接口缺少 records 数组")
    return payload["records"]


def reserve_topic(workflow: str, topic: str, fingerprint: str, days: int) -> dict:
    payload = _request(
        "POST",
        "/v1/topics/reserve",
        body={"workflow": workflow, "topic": topic, "fingerprint": fingerprint, "days": days},
    )
    if not isinstance(payload, dict) or not isinstance(payload.get("record"), dict):
        raise CloudflareDataRequestError("Cloudflare 话题占用接口缺少 record 对象")
    return payload["record"]


def commit_publication(
    *,
    publication_id: str,
    workflow: str,
    topic: str,
    fingerprint: str,
    days: int,
    entries: list[dict] | None = None,
    history_days: int = 100,
    minimum_new_words: int = 5,
) -> dict:
    payload = _request(
        "POST",
        "/v1/publications/commit",
        body={
            "publication_id": publication_id,
            "workflow": workflow,
            "topic": topic,
            "fingerprint": fingerprint,
            "days": days,
            "entries": entries or [],
            "history_days": history_days,
            "minimum_new_words": minimum_new_words,
        },
    )
    if not isinstance(payload, dict) or not isinstance(payload.get("record"), dict):
        raise CloudflareDataRequestError("Cloudflare 发布入库接口缺少 record 对象")
    return payload


def list_recent_words(days: int) -> list[str]:
    payload = _request("GET", "/v1/words/recent", query={"days": days})
    if not isinstance(payload, dict) or not isinstance(payload.get("words"), list):
        raise CloudflareDataRequestError("Cloudflare 单词历史接口缺少 words 数组")
    return [str(item) for item in payload["words"]]


def validate_and_record_words(
    *,
    workflow: str,
    run_id: str,
    topic: str,
    entries: list[dict],
    history_days: int,
    minimum_new_words: int,
) -> dict:
    payload = _request(
        "POST",
        "/v1/words/validate-and-record",
        body={
            "workflow": workflow,
            "run_id": run_id,
            "topic": topic,
            "entries": entries,
            "history_days": history_days,
            "minimum_new_words": minimum_new_words,
        },
    )
    if not isinstance(payload, dict):
        raise CloudflareDataRequestError("Cloudflare 单词历史接口响应格式不正确")
    return payload


def list_images(line: str) -> list[dict]:
    payload = _request("GET", "/v1/images", query={"line": line})
    if not isinstance(payload, dict) or not isinstance(payload.get("records"), list):
        raise CloudflareDataRequestError("Cloudflare 图库接口缺少 records 数组")
    return payload["records"]
