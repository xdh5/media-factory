"""通过 YouTube Data API 发布视频；OAuth 客户端共用，频道凭据按账号前缀隔离。"""

from __future__ import annotations

import mimetypes
import os
import re
import time
from datetime import datetime, timezone
from pathlib import Path
from typing import Callable

from google.auth.transport.requests import Request
from google.oauth2.credentials import Credentials
from googleapiclient.discovery import build
from googleapiclient.errors import HttpError
from googleapiclient.http import MediaFileUpload

from ._constants import (
    ACCOUNT_ID_PATTERN,
    DEFAULT_CATEGORY_ID,
    DEFAULT_LANGUAGE,
    MAX_TRANSIENT_RETRIES,
    UPLOAD_CHUNK_SIZE,
    YOUTUBE_CHANNEL_ID_SUFFIX,
    YOUTUBE_CHANNEL_TITLE_SUFFIX,
    YOUTUBE_OAUTH_CLIENT_ID_ENV,
    YOUTUBE_OAUTH_CLIENT_SECRET_ENV,
    YOUTUBE_PRIVACY_STATUSES,
    YOUTUBE_REFRESH_TOKEN_SUFFIX,
    YOUTUBE_REQUIRED_SUFFIXES,
    YOUTUBE_SCOPES,
    YOUTUBE_TOKEN_SUFFIX,
    YOUTUBE_TOKEN_URI,
    load_project_env,
)
from ._errors import AccountNotFoundError, CredentialError, InvalidParameterError, UploadError

__all__ = ["list_youtube_accounts", "publish_to_youtube"]

load_project_env()


def _env(name: str) -> str:
    return os.getenv(name, "").strip()


def _normalize_account(account: str) -> str:
    value = str(account or "").strip().lower()
    if not re.fullmatch(ACCOUNT_ID_PATTERN, value):
        raise InvalidParameterError(
            f"account 必须是小写字母开头的标识，例如 language_learning，当前为 {account!r}",
            {"parameter": "account"},
        )
    return value


def _account_from_prefix(prefix: str) -> str:
    return str(prefix).strip().lower()


def _youtube_settings(prefix: str) -> dict[str, str] | None:
    values = {suffix: _env(prefix + suffix) for suffix in YOUTUBE_REQUIRED_SUFFIXES}
    values[YOUTUBE_OAUTH_CLIENT_ID_ENV] = _env(YOUTUBE_OAUTH_CLIENT_ID_ENV)
    values[YOUTUBE_OAUTH_CLIENT_SECRET_ENV] = _env(YOUTUBE_OAUTH_CLIENT_SECRET_ENV)
    if any(not value for value in values.values()):
        return None
    values[YOUTUBE_TOKEN_SUFFIX] = _env(prefix + YOUTUBE_TOKEN_SUFFIX)
    values[YOUTUBE_CHANNEL_TITLE_SUFFIX] = _env(prefix + YOUTUBE_CHANNEL_TITLE_SUFFIX)
    return values


def _discover_prefixes() -> list[str]:
    load_project_env()
    prefixes = []
    for key in os.environ:
        if key.endswith(YOUTUBE_CHANNEL_ID_SUFFIX):
            prefix = key[: -len(YOUTUBE_CHANNEL_ID_SUFFIX)]
            if prefix and _youtube_settings(prefix):
                prefixes.append(prefix)
    return sorted(set(prefixes), key=str.lower)


def list_youtube_accounts(account: str | None = None) -> list[dict]:
    """列出 .env 里已配齐的 YouTube 账号。account 传入时只返回该号。"""
    wanted = _normalize_account(account) if account else None
    accounts = []
    for prefix in _discover_prefixes():
        slug = _account_from_prefix(prefix)
        if wanted and slug != wanted:
            continue
        settings = _youtube_settings(prefix)
        if not settings:
            continue
        accounts.append({
            "account": slug,
            "channel_id": settings[YOUTUBE_CHANNEL_ID_SUFFIX],
            "channel_title": settings[YOUTUBE_CHANNEL_TITLE_SUFFIX] or slug,
            "thumbnail_url": "",
        })
    return accounts


def _load_credentials(channel_id: str, account: str | None = None) -> Credentials:
    normalized = str(channel_id).strip()
    if not normalized:
        raise InvalidParameterError("channel_id 不能为空", {"parameter": "channel_id"})
    matched = [
        item for item in list_youtube_accounts(account)
        if item["channel_id"] == normalized
    ]
    if not matched:
        raise AccountNotFoundError(
            f"找不到 YouTube 频道 {normalized}。请在 .env 按账号前缀填写 "
            f"{{ACCOUNT}}_YOUTUBE_CHANNEL_ID / {{ACCOUNT}}_YOUTUBE_REFRESH_TOKEN，"
            f"并填写共用的 {YOUTUBE_OAUTH_CLIENT_ID_ENV} / {YOUTUBE_OAUTH_CLIENT_SECRET_ENV}",
            {"channel_id": normalized, "account": account},
        )
    prefix = matched[0]["account"].upper()
    settings = _youtube_settings(prefix)
    if settings is None:
        raise CredentialError(
            f"YouTube 账号 {matched[0]['account']} 凭据不完整",
            {"account": matched[0]["account"]},
        )
    credentials = Credentials(
        token=settings[YOUTUBE_TOKEN_SUFFIX] or None,
        refresh_token=settings[YOUTUBE_REFRESH_TOKEN_SUFFIX],
        token_uri=YOUTUBE_TOKEN_URI,
        client_id=settings[YOUTUBE_OAUTH_CLIENT_ID_ENV],
        client_secret=settings[YOUTUBE_OAUTH_CLIENT_SECRET_ENV],
        scopes=YOUTUBE_SCOPES,
    )
    try:
        if not credentials.valid:
            credentials.refresh(Request())
        return credentials
    except CredentialError:
        raise
    except Exception as exc:
        raise CredentialError(
            f"刷新 YouTube 频道 {normalized} 的登录态失败：{exc}",
            {
                "channel_id": normalized,
                "account": matched[0]["account"],
                "fix": f"请确认 .env 里 {prefix}{YOUTUBE_REFRESH_TOKEN_SUFFIX} 有效，且能访问 Google",
            },
        ) from exc


def _normalize_publish_at(publish_at: str | None) -> str | None:
    """校验定时时间并转换为 YouTube 接受的 UTC ISO 8601。"""
    value = str(publish_at or "").strip()
    if not value:
        return None
    try:
        parsed = datetime.fromisoformat(value.replace("Z", "+00:00"))
    except ValueError as exc:
        raise InvalidParameterError(
            "publish_at 必须是带时区的 ISO 8601 时间，例如 2026-08-23T16:00:00+08:00",
            {"parameter": "publish_at", "value": value},
        ) from exc
    if parsed.tzinfo is None or parsed.utcoffset() is None:
        raise InvalidParameterError(
            "publish_at 必须明确包含时区，例如北京时间使用 +08:00",
            {"parameter": "publish_at", "value": value},
        )
    normalized = parsed.astimezone(timezone.utc).replace(microsecond=0)
    if normalized <= datetime.now(timezone.utc):
        raise InvalidParameterError(
            "publish_at 必须是未来时间",
            {"parameter": "publish_at", "value": value},
        )
    return normalized.isoformat().replace("+00:00", "Z")


def _find_existing_video(youtube, channel_id: str, title: str) -> dict | None:
    """按精确标题查找频道里已有视频（含未公开/定时），避免重试时重复上传。"""
    wanted = str(title or "").strip()
    if not wanted:
        return None
    channel = youtube.channels().list(part="contentDetails", id=channel_id).execute()
    items = channel.get("items") or []
    if not items:
        return None
    uploads = str(
        ((items[0].get("contentDetails") or {}).get("relatedPlaylists") or {}).get("uploads") or ""
    ).strip()
    if not uploads:
        return None
    matches: list[dict] = []
    page_token = None
    scanned = 0
    while scanned < 250:
        response = youtube.playlistItems().list(
            part="snippet,contentDetails",
            playlistId=uploads,
            maxResults=50,
            pageToken=page_token,
        ).execute()
        for item in response.get("items") or []:
            scanned += 1
            snippet = item.get("snippet") or {}
            if str(snippet.get("title") or "").strip() != wanted:
                continue
            video_id = str(
                (snippet.get("resourceId") or {}).get("videoId")
                or (item.get("contentDetails") or {}).get("videoId")
                or ""
            ).strip()
            if video_id:
                matches.append({
                    "video_id": video_id,
                    "published_at": str(snippet.get("publishedAt") or ""),
                })
        page_token = response.get("nextPageToken")
        if not page_token:
            break
    if not matches:
        return None
    matches.sort(key=lambda item: item.get("published_at") or "")
    oldest = matches[0]
    oldest["duplicate_count"] = len(matches)
    return oldest


def publish_to_youtube(
    channel_id: str,
    video_path: str | Path,
    title: str,
    *,
    description: str = "",
    tags: list[str] | None = None,
    category_id: str = DEFAULT_CATEGORY_ID,
    privacy_status: str = "private",
    thumbnail_path: str | Path | None = None,
    caption_path: str | Path | None = None,
    language: str = DEFAULT_LANGUAGE,
    account: str | None = None,
    publish_at: str | None = None,
    on_progress: Callable[[float, str], None] | None = None,
) -> dict:
    """上传单个视频，可选设置封面、字幕和 YouTube 平台定时发布。"""
    video = Path(video_path).resolve()
    if not video.is_file():
        raise InvalidParameterError(f"视频文件不存在：{video}", {"parameter": "video_path"})
    normalized_title = str(title).strip()
    if not normalized_title:
        raise InvalidParameterError("title 不能为空", {"parameter": "title"})
    if privacy_status not in YOUTUBE_PRIVACY_STATUSES:
        raise InvalidParameterError(
            f"privacy_status 必须从 {YOUTUBE_PRIVACY_STATUSES} 中选择",
            {"parameter": "privacy_status"},
        )
    normalized_publish_at = _normalize_publish_at(publish_at)
    effective_privacy_status = "private" if normalized_publish_at else privacy_status
    normalized_tags = [str(tag).strip().lstrip("#") for tag in (tags or []) if str(tag).strip()]
    thumbnail = Path(thumbnail_path).resolve() if thumbnail_path else None
    caption = Path(caption_path).resolve() if caption_path else None
    credentials = _load_credentials(channel_id, account)
    try:
        with build("youtube", "v3", credentials=credentials) as youtube:
            existing = _find_existing_video(youtube, channel_id, normalized_title[:100])
            if existing:
                print(
                    f"[YouTube] 标题已存在 {existing.get('duplicate_count') or 1} 条，跳过上传 "
                    f"title={normalized_title[:100]!r} video_id={existing['video_id']}",
                    flush=True,
                )
                return {
                    "video_id": existing["video_id"],
                    "video_url": f"https://www.youtube.com/watch?v={existing['video_id']}",
                    "channel_id": channel_id,
                    "privacy_status": effective_privacy_status,
                    "publish_at": normalized_publish_at,
                    "scheduled": normalized_publish_at is not None,
                    "reused": True,
                    "duplicate_count": int(existing.get("duplicate_count") or 1),
                }
            video_status = {
                "privacyStatus": effective_privacy_status,
                "selfDeclaredMadeForKids": False,
                "embeddable": True,
                "license": "youtube",
            }
            if normalized_publish_at:
                video_status["publishAt"] = normalized_publish_at
            request = youtube.videos().insert(
                part="snippet,status",
                body={
                    "snippet": {
                        "title": normalized_title[:100],
                        "description": str(description),
                        "tags": normalized_tags[:500],
                        "categoryId": str(category_id),
                        "defaultLanguage": language,
                        "defaultAudioLanguage": language,
                    },
                    "status": video_status,
                },
                media_body=MediaFileUpload(
                    str(video), mimetype="video/*", resumable=True, chunksize=UPLOAD_CHUNK_SIZE,
                ),
            )
            response = None
            retries = 0
            while response is None:
                try:
                    status, response = request.next_chunk()
                    retries = 0
                    if status and on_progress:
                        progress = float(status.progress() or 0.0)
                        on_progress(progress, f"上传中 {int(progress * 100)}%")
                except Exception as exc:
                    code = int(getattr(getattr(exc, "resp", None), "status", 0) or 0)
                    transient = isinstance(exc, (TimeoutError, OSError)) or code == 429 or 500 <= code < 600
                    if not transient or retries >= MAX_TRANSIENT_RETRIES:
                        raise
                    retries += 1
                    time.sleep(min(30, 2 ** retries))
            video_id = str((response or {}).get("id") or "")
            if not video_id:
                raise UploadError("YouTube 未返回 video_id，上传失败")
            if thumbnail and thumbnail.is_file():
                mime = mimetypes.guess_type(thumbnail.name)[0] or "application/octet-stream"
                youtube.thumbnails().set(
                    videoId=video_id,
                    media_body=MediaFileUpload(str(thumbnail), mimetype=mime),
                ).execute()
            if caption and caption.is_file():
                youtube.captions().insert(
                    part="snippet",
                    body={"snippet": {"videoId": video_id, "language": language, "name": language, "isDraft": False}},
                    media_body=MediaFileUpload(str(caption), mimetype="text/plain"),
                ).execute()
    except UploadError:
        raise
    except HttpError as exc:
        raise UploadError(f"YouTube API 拒绝上传：{exc}", {"channel_id": channel_id}) from exc
    except Exception as exc:
        raise UploadError(f"YouTube 上传失败：{exc}", {"channel_id": channel_id}) from exc
    return {
        "video_id": video_id,
        "video_url": f"https://www.youtube.com/watch?v={video_id}",
        "channel_id": channel_id,
        "privacy_status": effective_privacy_status,
        "publish_at": normalized_publish_at,
        "scheduled": normalized_publish_at is not None,
    }
