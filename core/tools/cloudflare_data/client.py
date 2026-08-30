"""通过鉴权 Worker API 访问 Cloudflare D1。"""

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
            raise CloudflareDataConflictError(message, details, remote_code=code)
        raise CloudflareDataRequestError(message, {**details, "remote_code": code})
    except (CloudflareDataConflictError, CloudflareDataRequestError):
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


def list_image_library(*, line: str = "finance") -> list[dict]:
    payload = _request("GET", "/v1/image-library", query={"line": line})
    if not isinstance(payload, dict) or not isinstance(payload.get("records"), list):
        raise CloudflareDataRequestError("Cloudflare 存量图库接口缺少 records 数组")
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


def list_publication_records(
    *,
    business_line: str | None = None,
    platform: str | None = None,
    publish_date: str | None = None,
    run_id: str | None = None,
) -> list[dict]:
    query = {}
    if business_line:
        query["business_line"] = business_line
    if platform:
        query["platform"] = platform
    if publish_date:
        query["publish_date"] = publish_date
    if run_id:
        query["run_id"] = run_id
    payload = _request("GET", "/v1/publication-records", query=query)
    if not isinstance(payload, dict) or not isinstance(payload.get("records"), list):
        raise CloudflareDataRequestError("Cloudflare 发布记录接口缺少 records 数组")
    return payload["records"]


def commit_publication_records(records: list[dict]) -> dict:
    payload = _request("POST", "/v1/publication-records/commit", body={"records": records})
    if not isinstance(payload, dict) or not isinstance(payload.get("records"), list):
        raise CloudflareDataRequestError("Cloudflare 发布记录写入接口缺少 records 数组")
    return payload


def list_publishing_account_groups(*, business_line: str | None = None) -> dict:
    query = {"business_line": business_line} if business_line else None
    payload = _request("GET", "/v1/publishing-account-groups", query=query)
    if (
        not isinstance(payload, dict)
        or not isinstance(payload.get("groups"), list)
        or not isinstance(payload.get("members"), list)
    ):
        raise CloudflareDataRequestError("Cloudflare 发布账号组接口缺少 groups 或 members 数组")
    return payload


def list_production_outputs(
    *,
    publish_date: str | None = None,
    business_line: str | None = None,
    source: str | None = None,
) -> list[dict]:
    query = {}
    if publish_date:
        query["publish_date"] = publish_date
    if business_line:
        query["business_line"] = business_line
    if source:
        query["source"] = source
    payload = _request("GET", "/v1/production-outputs", query=query)
    if not isinstance(payload, dict) or not isinstance(payload.get("records"), list):
        raise CloudflareDataRequestError("Cloudflare 产物记录接口缺少 records 数组")
    return payload["records"]


def commit_production_outputs(records: list[dict]) -> dict:
    payload = _request("POST", "/v1/production-outputs/commit", body={"records": records})
    if not isinstance(payload, dict) or not isinstance(payload.get("records"), list):
        raise CloudflareDataRequestError("Cloudflare 产物记录写入接口缺少 records 数组")
    return payload


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


def get_douyin_research_script_stats(
    *,
    collection_code: str,
    workflow: str,
    reservation_minutes: int = 120,
) -> dict:
    payload = _request(
        "GET",
        "/v1/douyin-research/scripts/stats",
        query={
            "collection_code": collection_code,
            "workflow": workflow,
            "reservation_minutes": reservation_minutes,
        },
    )
    required_counts = ("total_count", "available_count", "reserved_count", "used_count")
    if not isinstance(payload, dict) or any(
        type(payload.get(name)) is not int or payload[name] < 0 for name in required_counts
    ):
        raise CloudflareDataRequestError("Cloudflare 稿件统计接口缺少有效的数量字段")
    if (
        not isinstance(payload.get("collection_code"), str)
        or not isinstance(payload.get("workflow"), str)
        or type(payload.get("reservation_minutes")) is not int
        or not isinstance(payload.get("checked_at"), str)
    ):
        raise CloudflareDataRequestError("Cloudflare 稿件统计接口缺少有效的查询信息")
    classified_count = sum(
        payload[name] for name in ("available_count", "reserved_count", "used_count")
    )
    if classified_count != payload["total_count"]:
        raise CloudflareDataRequestError("Cloudflare 稿件统计接口返回的分类数量与总数不一致")
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
