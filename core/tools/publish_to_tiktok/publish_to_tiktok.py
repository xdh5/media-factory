"""通过 Zernio HTTP API 把 R2 公网视频发布到 TikTok。"""

from __future__ import annotations

import os
import re
import uuid

import requests

from ._constants import (
    ACCOUNT_ID_PATTERN,
    TIKTOK_ACCOUNT_ID_SUFFIX,
    TIKTOK_ACCOUNT_TITLE_SUFFIX,
    TIKTOK_PRIVACY_LEVEL,
    TIKTOK_REQUEST_TIMEOUT_SECONDS,
    TIKTOK_USERNAME_SUFFIX,
    ZERNIO_API_BASE_URL,
    ZERNIO_API_KEY_ENV,
    ZERNIO_LEGACY_API_KEY_ENV,
    load_project_env,
)
from ._errors import AccountNotFoundError, CredentialError, InvalidParameterError, PublishError

__all__ = ["list_tiktok_accounts", "publish_to_tiktok"]

load_project_env()


def _env(name: str) -> str:
    return os.getenv(name, "").strip()


def _api_key() -> str:
    value = _env(ZERNIO_API_KEY_ENV) or _env(ZERNIO_LEGACY_API_KEY_ENV)
    if not value:
        raise CredentialError(
            f"缺少 {ZERNIO_API_KEY_ENV}，请把 Zernio API key 写入 MCP 宿主环境的 .env",
            {"environment": ZERNIO_API_KEY_ENV},
        )
    return value


def _normalize_account(account: str) -> str:
    value = str(account or "").strip().lower()
    if not re.fullmatch(ACCOUNT_ID_PATTERN, value):
        raise InvalidParameterError(
            f"account 必须是小写字母开头的标识，例如 language_learning，当前为 {account!r}",
            {"parameter": "account"},
        )
    return value


def list_tiktok_accounts(account: str | None = None) -> list[dict]:
    """列出本地已配置的 TikTok 账号；account 传入时只返回该账号。"""
    load_project_env()
    wanted = _normalize_account(account) if account else None
    accounts = []
    for key, value in os.environ.items():
        if not key.endswith(TIKTOK_ACCOUNT_ID_SUFFIX) or not str(value).strip():
            continue
        prefix = key[: -len(TIKTOK_ACCOUNT_ID_SUFFIX)]
        slug = prefix.lower()
        if wanted and slug != wanted:
            continue
        accounts.append({
            "account": slug,
            "account_id": str(value).strip(),
            "account_title": _env(prefix + TIKTOK_ACCOUNT_TITLE_SUFFIX) or slug,
            "username": _env(prefix + TIKTOK_USERNAME_SUFFIX),
        })
    return sorted(accounts, key=lambda item: item["account"])


def _configured_account(account_id: str, account: str | None) -> dict:
    normalized_id = str(account_id or "").strip()
    if not normalized_id:
        raise InvalidParameterError("account_id 不能为空", {"parameter": "account_id"})
    matches = [
        item for item in list_tiktok_accounts(account)
        if item["account_id"] == normalized_id
    ]
    if not matches:
        raise AccountNotFoundError(
            f"找不到 TikTok 账号 {normalized_id}。请配置 {{ACCOUNT}}{TIKTOK_ACCOUNT_ID_SUFFIX}",
            {"account_id": normalized_id, "account": account},
        )
    return matches[0]


def publish_to_tiktok(
    account_id: str,
    video_url: str,
    content: str,
    *,
    account: str | None = None,
) -> dict:
    """立即公开发布单个 TikTok 视频。"""
    configured = _configured_account(account_id, account)
    normalized_url = str(video_url or "").strip()
    if not normalized_url.startswith(("https://", "http://")):
        raise InvalidParameterError("video_url 必须是 R2 的 HTTP(S) 公网地址", {"parameter": "video_url"})
    normalized_content = str(content or "").strip()
    if len(normalized_content) > 2200:
        raise InvalidParameterError("TikTok content 不能超过 2200 个字符", {"parameter": "content"})
    request_id = str(uuid.uuid5(uuid.NAMESPACE_URL, f"{configured['account_id']}|{normalized_url}|{normalized_content}"))
    payload = {
        "content": normalized_content,
        "mediaItems": [{"type": "video", "url": normalized_url}],
        "platforms": [{"platform": "tiktok", "accountId": configured["account_id"]}],
        "tiktokSettings": {
            "privacy_level": TIKTOK_PRIVACY_LEVEL,
            "allow_comment": True,
            "allow_duet": True,
            "allow_stitch": True,
            "content_preview_confirmed": True,
            "express_consent_given": True,
            "video_made_with_ai": True,
            "commercialContentType": "none",
        },
        "publishNow": True,
    }
    try:
        response = requests.post(
            f"{ZERNIO_API_BASE_URL}/posts",
            headers={
                "Authorization": f"Bearer {_api_key()}",
                "Content-Type": "application/json",
                "x-request-id": request_id,
            },
            json=payload,
            timeout=TIKTOK_REQUEST_TIMEOUT_SECONDS,
        )
    except requests.RequestException as exc:
        raise PublishError(f"请求 Zernio 发布 TikTok 失败：{exc}", {"account_id": account_id}) from exc
    try:
        result = response.json()
    except ValueError:
        result = {}
    if response.status_code == 409:
        details = result.get("details") if isinstance(result, dict) else {}
        post_id = str((details or {}).get("existingPostId") or "")
        if post_id:
            return {"post_id": post_id, "platform_url": "", "account_id": account_id, "duplicate": True}
    if not response.ok:
        message = str(result.get("error") or result.get("message") or response.text[:500])
        raise PublishError(
            f"Zernio 拒绝发布 TikTok：HTTP {response.status_code}，{message}",
            {"account_id": account_id, "status_code": response.status_code},
        )
    post = result.get("post") or result.get("data") or result
    if not isinstance(post, dict):
        post = {}
    post_id = str(post.get("_id") or post.get("id") or result.get("postId") or "")
    platform_url = str(post.get("platformPostUrl") or result.get("platformPostUrl") or "")
    if not post_id:
        raise PublishError("Zernio 未返回 post ID，无法确认 TikTok 发布任务", {"account_id": account_id})
    return {"post_id": post_id, "platform_url": platform_url, "account_id": account_id, "duplicate": False}
