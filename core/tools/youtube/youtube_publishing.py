"""通过 YouTube Data API 发布视频并管理项目内 OAuth 登录态。"""

from __future__ import annotations

import json
import mimetypes
import shutil
import time
from datetime import datetime
from pathlib import Path
from typing import Callable

from google.auth.transport.requests import Request
from google.oauth2.credentials import Credentials
from googleapiclient.discovery import build
from googleapiclient.errors import HttpError
from googleapiclient.http import MediaFileUpload

from ._constants import (
    DEFAULT_CATEGORY_ID,
    DEFAULT_LANGUAGE,
    MAX_TRANSIENT_RETRIES,
    UPLOAD_CHUNK_SIZE,
    YOUTUBE_PRIVACY_STATUSES,
    YOUTUBE_SCOPES,
    YOUTUBE_TOKEN_DIR,
)
from ._errors import AccountNotFoundError, CredentialError, InvalidParameterError, MigrationError, UploadError

__all__ = ["list_youtube_accounts", "publish_youtube_video", "migrate_youtube_accounts"]


def _read_token(channel_id: str) -> tuple[Path, dict]:
    normalized = str(channel_id).strip()
    if not normalized:
        raise InvalidParameterError("channel_id 不能为空", {"parameter": "channel_id"})
    path = YOUTUBE_TOKEN_DIR / f"{normalized}.json"
    if not path.is_file():
        raise AccountNotFoundError(
            f"YouTube 频道 {normalized} 未授权，请先迁移或重新授权账号",
            {"channel_id": normalized, "token_path": str(path)},
        )
    try:
        return path, json.loads(path.read_text(encoding="utf-8"))
    except (OSError, ValueError, TypeError) as exc:
        raise CredentialError(f"YouTube 频道 {normalized} 的凭据文件已损坏", {"token_path": str(path)}) from exc


def _credentials(data: dict) -> Credentials:
    payload = data.get("credentials") or {}
    expiry = payload.get("expiry")
    return Credentials(
        token=payload.get("token"),
        refresh_token=payload.get("refresh_token"),
        token_uri=payload.get("token_uri") or "https://oauth2.googleapis.com/token",
        client_id=payload.get("client_id"),
        client_secret=payload.get("client_secret"),
        scopes=payload.get("scopes") or YOUTUBE_SCOPES,
        expiry=datetime.fromisoformat(expiry) if expiry else None,
    )


def _save_token(path: Path, data: dict, credentials: Credentials) -> None:
    data["credentials"] = {
        "token": credentials.token,
        "refresh_token": credentials.refresh_token,
        "token_uri": credentials.token_uri,
        "client_id": credentials.client_id,
        "client_secret": credentials.client_secret,
        "scopes": credentials.scopes,
        "expiry": credentials.expiry.isoformat() if credentials.expiry else None,
    }
    data["updated_at"] = int(time.time())
    temporary = path.with_suffix(".json.tmp")
    temporary.write_text(json.dumps(data, ensure_ascii=False, indent=2), encoding="utf-8")
    temporary.replace(path)


def _load_credentials(channel_id: str) -> Credentials:
    path, data = _read_token(channel_id)
    try:
        credentials = _credentials(data)
        if credentials.expired:
            if not credentials.refresh_token:
                raise CredentialError(f"YouTube 频道 {channel_id} 的刷新令牌缺失，请重新授权")
            credentials.refresh(Request())
            _save_token(path, data, credentials)
        return credentials
    except CredentialError:
        raise
    except Exception as exc:
        raise CredentialError(
            f"刷新 YouTube 频道 {channel_id} 的登录态失败：{exc}",
            {"channel_id": channel_id, "fix": "请确认网络可访问 Google，或重新授权账号"},
        ) from exc


def list_youtube_accounts() -> list[dict]:
    YOUTUBE_TOKEN_DIR.mkdir(parents=True, exist_ok=True)
    accounts = []
    for path in YOUTUBE_TOKEN_DIR.glob("*.json"):
        try:
            data = json.loads(path.read_text(encoding="utf-8"))
        except (OSError, ValueError, TypeError):
            continue
        accounts.append({
            "channel_id": str(data.get("channel_id") or path.stem),
            "channel_title": str(data.get("channel_title") or path.stem),
            "thumbnail_url": str(data.get("thumbnail_url") or ""),
        })
    return sorted(accounts, key=lambda item: item["channel_title"])


def publish_youtube_video(
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
    on_progress: Callable[[float, str], None] | None = None,
) -> dict:
    """上传单个视频，可选设置封面和字幕。"""
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
    normalized_tags = [str(tag).strip().lstrip("#") for tag in (tags or []) if str(tag).strip()]
    thumbnail = Path(thumbnail_path).resolve() if thumbnail_path else None
    caption = Path(caption_path).resolve() if caption_path else None
    credentials = _load_credentials(channel_id)
    try:
        with build("youtube", "v3", credentials=credentials) as youtube:
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
                    "status": {
                        "privacyStatus": privacy_status,
                        "selfDeclaredMadeForKids": False,
                        "embeddable": True,
                        "license": "youtube",
                    },
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
    return {"video_id": video_id, "video_url": f"https://www.youtube.com/watch?v={video_id}", "channel_id": channel_id}


def migrate_youtube_accounts(
    source_token_dir: str | Path,
    channel_ids: list[str] | None = None,
) -> dict:
    """把已有 OAuth 令牌和账号组复制到项目，不输出令牌内容。"""
    source = Path(source_token_dir).resolve()
    if not source.is_dir():
        raise MigrationError(f"YouTube 令牌目录不存在：{source}", {"source_token_dir": str(source)})
    YOUTUBE_TOKEN_DIR.mkdir(parents=True, exist_ok=True)
    selected = {str(channel_id).strip() for channel_id in (channel_ids or []) if str(channel_id).strip()}
    copied = 0
    for path in source.glob("*.json"):
        if selected and path.stem not in selected:
            continue
        try:
            data = json.loads(path.read_text(encoding="utf-8"))
            if not isinstance(data.get("credentials"), dict):
                continue
            shutil.copy2(path, YOUTUBE_TOKEN_DIR / path.name)
            copied += 1
        except (OSError, ValueError, TypeError) as exc:
            raise MigrationError(f"迁移 YouTube 凭据失败：{path.name}：{exc}") from exc
    accounts = list_youtube_accounts()
    return {
        "source_token_dir": str(source),
        "target_token_dir": str(YOUTUBE_TOKEN_DIR),
        "copied": copied,
        "accounts": accounts,
    }
