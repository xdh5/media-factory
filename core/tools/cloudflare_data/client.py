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


def list_finance_generated_images() -> list[dict]:
    payload = _request("GET", "/v1/finance-generated-images")
    if not isinstance(payload, dict) or not isinstance(payload.get("records"), list):
        raise CloudflareDataRequestError("Cloudflare 财经生成图库接口缺少 records 数组")
    return payload["records"]


def commit_finance_generated_images(records: list[dict]) -> dict:
    payload = _request(
        "POST",
        "/v1/finance-generated-images/commit",
        body={"records": records},
    )
    if not isinstance(payload, dict) or not isinstance(payload.get("records"), list):
        raise CloudflareDataRequestError("Cloudflare 财经生成图库写入接口缺少 records 数组")
    return payload


def list_publish_account_groups() -> list[dict]:
    payload = _request("GET", "/v1/publish-account-groups")
    if not isinstance(payload, dict) or not isinstance(payload.get("records"), list):
        raise CloudflareDataRequestError("Cloudflare 发布账号组接口缺少 records 数组")
    return payload["records"]


def get_publish_account_group(group: str) -> dict:
    group_name = str(group or "").strip()
    if not group_name:
        raise CloudflareDataRequestError("发布账号组编码或名称不能为空")
    payload = _request("GET", "/v1/publish-account-groups", query={"group": group_name})
    if not isinstance(payload, dict) or not isinstance(payload.get("records"), list):
        raise CloudflareDataRequestError("Cloudflare 发布账号组接口缺少 records 数组")
    if len(payload["records"]) != 1 or not isinstance(payload["records"][0], dict):
        raise CloudflareDataRequestError(
            f"Cloudflare 发布账号组接口没有返回唯一账号组：{group_name}",
            {"group": group_name, "record_count": len(payload["records"])},
        )
    return payload["records"][0]


def list_douyin_research_ids() -> list[str]:
    payload = _request("GET", "/v1/douyin-research/ids")
    if not isinstance(payload, dict) or not isinstance(payload.get("aweme_ids"), list):
        raise CloudflareDataRequestError("Cloudflare 抖音研究去重接口缺少 aweme_ids 数组")
    return [str(value) for value in payload["aweme_ids"] if str(value).strip()]


def commit_douyin_research(records: list[dict]) -> dict:
    payload = _request(
        "POST",
        "/v1/douyin-research/commit",
        body={"records": records},
    )
    if not isinstance(payload, dict) or not isinstance(payload.get("records"), list):
        raise CloudflareDataRequestError("Cloudflare 抖音研究写入接口缺少 records 数组")
    return payload


def reserve_douyin_research_script(
    *,
    collection_code: str,
    workflow: str,
    reservation_minutes: int = 120,
) -> dict:
    payload = _request(
        "POST",
        "/v1/douyin-research/scripts/reserve",
        body={
            "collection_code": collection_code,
            "workflow": workflow,
            "reservation_minutes": reservation_minutes,
        },
    )
    if not isinstance(payload, dict):
        raise CloudflareDataRequestError("Cloudflare 财经稿件选择接口响应格式不正确")
    if not isinstance(payload.get("source"), dict) or not isinstance(payload.get("reservation"), dict):
        raise CloudflareDataRequestError("Cloudflare 财经稿件选择接口缺少 source 或 reservation 对象")
    return payload


def mark_douyin_research_script_used(
    *,
    aweme_id: str,
    workflow: str,
    reservation_token: str,
    run_id: str,
    source_hook: str,
) -> dict:
    payload = _request(
        "POST",
        "/v1/douyin-research/scripts/used",
        body={
            "aweme_id": aweme_id,
            "workflow": workflow,
            "reservation_token": reservation_token,
            "run_id": run_id,
            "source_hook": source_hook,
        },
    )
    if not isinstance(payload, dict) or not isinstance(payload.get("record"), dict):
        raise CloudflareDataRequestError("Cloudflare 财经稿件使用标记接口缺少 record 对象")
    return payload
