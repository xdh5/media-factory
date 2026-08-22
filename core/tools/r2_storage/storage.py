"""上传和删除 Cloudflare R2 公开对象。"""

from __future__ import annotations

import os
from pathlib import Path
from urllib.parse import quote

import boto3
from botocore.config import Config

from ._constants import R2_DOWNLOAD_TIMEOUT_SECONDS, R2_REGION, R2_REQUIRED_ENV, R2_UPLOAD_TIMEOUT_SECONDS, load_project_env
from ._errors import CredentialError, DownloadError, InvalidParameterError, UploadError

load_project_env()

__all__ = ["upload_public_file", "download_public_file", "delete_public_file"]


def _env(name: str) -> str:
    return os.getenv(name, "").strip()


def _settings() -> dict:
    load_project_env()
    values = {name: _env(name) for name in R2_REQUIRED_ENV}
    missing = [name for name, value in values.items() if not value]
    if missing:
        raise CredentialError(
            f"缺少 Cloudflare R2 配置：{', '.join(missing)}。请在 .env 填写后重试",
            {"required": list(R2_REQUIRED_ENV), "missing": missing},
        )
    return values


def _client(account_id: str, access_key: str, secret: str):
    return boto3.client(
        "s3",
        endpoint_url=f"https://{account_id}.r2.cloudflarestorage.com",
        aws_access_key_id=access_key,
        aws_secret_access_key=secret,
        region_name=R2_REGION,
        config=Config(
            signature_version="s3v4",
            connect_timeout=30,
            read_timeout=R2_UPLOAD_TIMEOUT_SECONDS,
        ),
    )


def _normalize_key(object_key: str) -> str:
    key = str(object_key or "").strip().lstrip("/")
    if not key or ".." in key.split("/"):
        raise InvalidParameterError("object_key 必须是不含 .. 的相对路径", {"parameter": "object_key"})
    return key


def upload_public_file(file_path: str | Path, object_key: str, *, content_type: str = "video/mp4") -> dict:
    """上传文件并返回公开 URL。"""
    source = Path(file_path).resolve()
    if not source.is_file():
        raise InvalidParameterError(f"要上传的文件不存在：{source}", {"parameter": "file_path"})
    key = _normalize_key(object_key)
    settings = _settings()
    client = _client(settings["R2_ACCOUNT_ID"], settings["R2_ACCESS_KEY_ID"], settings["R2_SECRET_ACCESS_KEY"])
    try:
        client.upload_file(
            str(source),
            settings["R2_BUCKET"],
            key,
            ExtraArgs={"ContentType": str(content_type or "video/mp4")},
        )
    except Exception as exc:
        raise UploadError(
            f"上传到 Cloudflare R2 失败：{exc}",
            {"bucket": settings["R2_BUCKET"], "key": key, "fix": "请确认 R2 密钥有目标桶写权限"},
        ) from exc
    return {
        "url": f"{settings['R2_PUBLIC_BASE_URL'].rstrip('/')}/{quote(key, safe='/')}",
        "key": key,
        "bucket": settings["R2_BUCKET"],
        "size": source.stat().st_size,
    }


def download_public_file(object_key: str, destination_path: str | Path) -> dict:
    """从 R2 下载对象到指定本地文件。"""
    key = _normalize_key(object_key)
    destination = Path(destination_path).resolve()
    if destination.exists() and not destination.is_file():
        raise InvalidParameterError(
            f"destination_path 已存在且不是文件：{destination}",
            {"parameter": "destination_path"},
        )
    destination.parent.mkdir(parents=True, exist_ok=True)
    settings = _settings()
    client = boto3.client(
        "s3",
        endpoint_url=f"https://{settings['R2_ACCOUNT_ID']}.r2.cloudflarestorage.com",
        aws_access_key_id=settings["R2_ACCESS_KEY_ID"],
        aws_secret_access_key=settings["R2_SECRET_ACCESS_KEY"],
        region_name=R2_REGION,
        config=Config(
            signature_version="s3v4",
            connect_timeout=30,
            read_timeout=R2_DOWNLOAD_TIMEOUT_SECONDS,
        ),
    )
    temporary = destination.with_name(f"{destination.name}.part")
    try:
        client.download_file(settings["R2_BUCKET"], key, str(temporary))
        temporary.replace(destination)
    except Exception as exc:
        temporary.unlink(missing_ok=True)
        raise DownloadError(
            f"从 Cloudflare R2 下载失败：{exc}",
            {"bucket": settings["R2_BUCKET"], "key": key, "destination_path": str(destination)},
        ) from exc
    return {
        "path": str(destination),
        "key": key,
        "bucket": settings["R2_BUCKET"],
        "size": destination.stat().st_size,
    }


def delete_public_file(object_key: str) -> dict:
    """删除 R2 对象；对象不存在也视为成功。"""
    key = _normalize_key(object_key)
    settings = _settings()
    client = _client(settings["R2_ACCOUNT_ID"], settings["R2_ACCESS_KEY_ID"], settings["R2_SECRET_ACCESS_KEY"])
    try:
        client.delete_object(Bucket=settings["R2_BUCKET"], Key=key)
    except Exception as exc:
        raise UploadError(
            f"从 Cloudflare R2 删除失败：{exc}",
            {"bucket": settings["R2_BUCKET"], "key": key},
        ) from exc
    return {"deleted": True, "key": key, "bucket": settings["R2_BUCKET"]}
