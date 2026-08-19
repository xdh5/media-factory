"""把本地文件上传到 Cloudflare R2，返回 Meta 可拉取的公开 HTTPS 地址。"""

from __future__ import annotations

import os
from pathlib import Path
from urllib.parse import quote

import boto3
from botocore.config import Config
from dotenv import load_dotenv

from ._constants import R2_REGION, R2_REQUIRED_ENV, R2_UPLOAD_TIMEOUT_SECONDS
from ._errors import CredentialError, InvalidParameterError, UploadError

load_dotenv()

__all__ = ["upload_public_file", "delete_public_file"]


def _env(name: str) -> str:
    return os.getenv(name, "").strip()


def _settings() -> dict:
    values = {name: _env(name) for name in R2_REQUIRED_ENV}
    missing = [name for name, value in values.items() if not value]
    if missing:
        raise CredentialError(
            f"缺少 Cloudflare R2 配置：{', '.join(missing)}。请在 .env 填写后重试",
            {"required": list(R2_REQUIRED_ENV), "missing": missing},
        )
    return values


def _client(account_id: str, access_key: str, secret: str):
    endpoint = f"https://{account_id}.r2.cloudflarestorage.com"
    return boto3.client(
        "s3",
        endpoint_url=endpoint,
        aws_access_key_id=access_key,
        aws_secret_access_key=secret,
        region_name=R2_REGION,
        config=Config(
            signature_version="s3v4",
            connect_timeout=30,
            read_timeout=R2_UPLOAD_TIMEOUT_SECONDS,
        ),
    )


def _public_url(base: str, key: str) -> str:
    return f"{base.rstrip('/')}/{quote(key, safe='/')}"


def _normalize_key(object_key: str) -> str:
    key = str(object_key or "").strip().lstrip("/")
    if not key or ".." in key.split("/"):
        raise InvalidParameterError("object_key 必须是不含 .. 的相对路径", {"parameter": "object_key"})
    return key


def upload_public_file(
    file_path: str | Path,
    object_key: str,
    *,
    content_type: str = "video/mp4",
) -> dict:
    """上传对象并返回公开 URL。桶必须已开启公开读，Meta 才能抓取。"""
    source = Path(file_path).resolve()
    if not source.is_file():
        raise InvalidParameterError(f"要上传的文件不存在：{source}", {"parameter": "file_path"})
    key = _normalize_key(object_key)
    settings = _settings()
    client = _client(settings["R2_ACCOUNT_ID"], settings["R2_ACCESS_KEY_ID"], settings["R2_SECRET_ACCESS_KEY"])
    size = source.stat().st_size
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
            {"bucket": settings["R2_BUCKET"], "key": key, "fix": "请确认 API Token 对桶有写权限，且 Account ID 正确"},
        ) from exc
    return {
        "url": _public_url(settings["R2_PUBLIC_BASE_URL"], key),
        "key": key,
        "bucket": settings["R2_BUCKET"],
        "size": size,
    }


def delete_public_file(object_key: str) -> dict:
    """删除 R2 上的公开对象；对象不存在也视为成功。"""
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
