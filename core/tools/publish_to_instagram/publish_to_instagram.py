"""通过 Instagram Graph API 发布 Reels。"""

from __future__ import annotations

import os
import time

import requests

from ._constants import (
    DEFAULT_META_GRAPH_API_VERSION,
    FACEBOOK_PAGE_ACCESS_TOKEN_ENV,
    FAILURE_STATUS_CODES,
    INSTAGRAM_ACCESS_TOKEN_ENV,
    INSTAGRAM_ACCOUNT_TITLE_ENV,
    INSTAGRAM_USERNAME_ENV,
    INSTAGRAM_USER_ID_ENV,
    META_GRAPH_API_BASE_URL,
    META_GRAPH_API_VERSION_ENV,
    REQUEST_TIMEOUT_SECONDS,
    STATUS_POLL_INTERVAL_SECONDS,
    STATUS_TIMEOUT_SECONDS,
    SUCCESS_STATUS_CODES,
    load_project_env,
)
from ._errors import CredentialError, InvalidParameterError, PublishError

__all__ = ["list_instagram_accounts", "publish_to_instagram"]

load_project_env()


def _env(name: str) -> str:
    return os.getenv(name, "").strip()


def _settings(user_id: str) -> tuple[str, str, str]:
    configured_user_id = _env(INSTAGRAM_USER_ID_ENV)
    page_access_token = _env(FACEBOOK_PAGE_ACCESS_TOKEN_ENV)
    instagram_access_token = _env(INSTAGRAM_ACCESS_TOKEN_ENV)
    access_token = page_access_token or instagram_access_token
    if not configured_user_id or not access_token:
        raise CredentialError(
            f"缺少 {INSTAGRAM_USER_ID_ENV} 或官方 Graph API 访问令牌",
            {
                "fix": (
                    f"请在 .env 配置 Instagram 专业账号 ID，以及 {FACEBOOK_PAGE_ACCESS_TOKEN_ENV} "
                    f"或 {INSTAGRAM_ACCESS_TOKEN_ENV}"
                )
            },
        )
    normalized_user_id = str(user_id or "").strip()
    if normalized_user_id != configured_user_id:
        raise CredentialError(
            "请求的 Instagram 用户 ID 与本机配置不一致",
            {"requested_user_id": normalized_user_id},
        )
    version = _env(META_GRAPH_API_VERSION_ENV) or DEFAULT_META_GRAPH_API_VERSION
    return configured_user_id, access_token, version


def list_instagram_accounts() -> list[dict]:
    """列出本机已配置的 Instagram Graph API 账号。"""
    load_project_env()
    user_id = _env(INSTAGRAM_USER_ID_ENV)
    if not user_id or not (
        _env(FACEBOOK_PAGE_ACCESS_TOKEN_ENV) or _env(INSTAGRAM_ACCESS_TOKEN_ENV)
    ):
        return []
    return [{
        "user_id": user_id,
        "account_title": _env(INSTAGRAM_ACCOUNT_TITLE_ENV) or "Instagram",
        "username": _env(INSTAGRAM_USERNAME_ENV),
    }]


def _graph_error(response: requests.Response) -> str:
    try:
        payload = response.json()
    except ValueError:
        return response.text[:500]
    error = payload.get("error") if isinstance(payload, dict) else None
    if isinstance(error, dict):
        return str(error.get("message") or error)
    return str(payload)


def _request(method: str, url: str, *, token: str, data: dict | None = None, params: dict | None = None) -> dict:
    values = dict(params or {})
    values["access_token"] = token
    try:
        response = requests.request(
            method,
            url,
            data=data,
            params=values,
            timeout=REQUEST_TIMEOUT_SECONDS,
        )
    except requests.RequestException as exc:
        raise PublishError(f"请求 Instagram Graph API 失败：{exc}") from exc
    if not response.ok:
        raise PublishError(
            f"Instagram Graph API 返回 HTTP {response.status_code}：{_graph_error(response)}",
            {"status_code": response.status_code},
        )
    try:
        payload = response.json()
    except ValueError as exc:
        raise PublishError("Instagram Graph API 未返回 JSON") from exc
    return payload if isinstance(payload, dict) else {}


def _wait_container(container_id: str, *, token: str, version: str) -> None:
    deadline = time.monotonic() + STATUS_TIMEOUT_SECONDS
    url = f"{META_GRAPH_API_BASE_URL}/{version}/{container_id}"
    while True:
        payload = _request(
            "GET",
            url,
            token=token,
            params={"fields": "status_code,status"},
        )
        status_code = str(payload.get("status_code") or "").upper()
        if status_code in SUCCESS_STATUS_CODES:
            return
        if status_code in FAILURE_STATUS_CODES:
            raise PublishError(
                f"Instagram Reels 容器处理失败：{payload.get('status') or status_code}",
                {"container_id": container_id, "status_code": status_code},
            )
        if time.monotonic() >= deadline:
            raise PublishError(
                f"等待 Instagram Reels 处理超时，当前状态：{status_code or '未知'}",
                {"container_id": container_id, "status_code": status_code},
            )
        time.sleep(STATUS_POLL_INTERVAL_SECONDS)


def publish_to_instagram(
    user_id: str,
    video_url: str,
    caption: str,
    *,
    share_to_feed: bool = True,
) -> dict:
    """用公网视频 URL 创建并立即发布 Instagram Reel。"""
    normalized_url = str(video_url or "").strip()
    if not normalized_url.startswith(("https://", "http://")):
        raise InvalidParameterError("video_url 必须是 HTTP(S) 公网地址", {"parameter": "video_url"})
    normalized_caption = str(caption or "").strip()
    if len(normalized_caption) > 2200:
        raise InvalidParameterError("Instagram caption 不能超过 2200 个字符", {"parameter": "caption"})
    normalized_user_id, token, version = _settings(user_id)
    base = f"{META_GRAPH_API_BASE_URL}/{version}"
    created = _request(
        "POST",
        f"{base}/{normalized_user_id}/media",
        token=token,
        data={
            "media_type": "REELS",
            "video_url": normalized_url,
            "caption": normalized_caption,
            "share_to_feed": "true" if share_to_feed else "false",
        },
    )
    container_id = str(created.get("id") or "")
    if not container_id:
        raise PublishError("Instagram 未返回 Reels 容器 ID")
    _wait_container(container_id, token=token, version=version)
    published = _request(
        "POST",
        f"{base}/{normalized_user_id}/media_publish",
        token=token,
        data={"creation_id": container_id},
    )
    media_id = str(published.get("id") or "")
    if not media_id:
        raise PublishError("Instagram 未返回已发布媒体 ID")
    details = _request(
        "GET",
        f"{base}/{media_id}",
        token=token,
        params={"fields": "id,permalink"},
    )
    return {
        "media_id": media_id,
        "container_id": container_id,
        "permalink": str(details.get("permalink") or ""),
        "status": "published",
    }
