"""上传、下载和删除成片与图片文件。"""

from __future__ import annotations

import hashlib
import os
import shutil
import time
from concurrent.futures import ThreadPoolExecutor
from pathlib import Path
from urllib.parse import quote

import boto3
import requests
from botocore.config import Config

from ._constants import R2_DOWNLOAD_TIMEOUT_SECONDS, R2_REGION, R2_REQUIRED_ENV, R2_UPLOAD_TIMEOUT_SECONDS, load_project_env
from ._errors import CredentialError, DownloadError, InvalidParameterError, UploadError

load_project_env()

__all__ = ["upload_public_file", "download_public_file", "delete_public_file", "delete_public_files"]


def _env(name: str) -> str:
    return os.getenv(name, "").strip()


def _settings() -> dict:
    load_project_env()
    values = {name: _env(name) for name in R2_REQUIRED_ENV}
    missing = [name for name, value in values.items() if not value]
    if missing:
        raise CredentialError(
            f"缺少媒体文件存储配置：{', '.join(missing)}。请在 .env 填写后重试",
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
            f"上传媒体文件失败：{exc}",
            {"bucket": settings["R2_BUCKET"], "key": key, "fix": "请确认存储密钥有目标位置的写权限"},
        ) from exc
    return {
        "url": f"{settings['R2_PUBLIC_BASE_URL'].rstrip('/')}/{quote(key, safe='/')}",
        "key": key,
        "bucket": settings["R2_BUCKET"],
        "size": source.stat().st_size,
    }


def download_public_file(object_key: str, destination_path: str | Path) -> dict:
    """把成片或图片下载到指定本地文件。"""
    key = _normalize_key(object_key)
    destination = Path(destination_path).resolve()
    if destination.exists() and not destination.is_file():
        raise InvalidParameterError(
            f"destination_path 已存在且不是文件：{destination}",
            {"parameter": "destination_path"},
        )
    destination.parent.mkdir(parents=True, exist_ok=True)
    settings = _settings()
    url = f"{settings['R2_PUBLIC_BASE_URL'].rstrip('/')}/{quote(key, safe='/')}"
    temporary = destination.with_name(f"{destination.name}.part")
    try:
        with requests.head(url, timeout=(15, R2_DOWNLOAD_TIMEOUT_SECONDS)) as response:
            response.raise_for_status()
            total_size = int(response.headers["Content-Length"])
            etag = response.headers["ETag"]
        # 每段单独保存，断线只重试该段；对象版本变化时不复用旧片段。
        segment_size = 2 * 1024 * 1024
        version = hashlib.sha256(etag.encode()).hexdigest()[:16]
        segments = destination.with_name(f"{destination.name}.parts-{version}")
        segments.mkdir(exist_ok=True)

        def download_segment(start: int) -> Path:
            end = min(start + segment_size, total_size) - 1
            segment = segments / str(start)
            expected_size = end - start + 1
            if segment.is_file() and segment.stat().st_size == expected_size:
                return segment
            for attempt in range(4):
                try:
                    with requests.get(
                        url, headers={"Range": f"bytes={start}-{end}", "If-Match": etag,
                                      "Accept-Encoding": "identity"},
                        stream=True, timeout=(15, R2_DOWNLOAD_TIMEOUT_SECONDS),
                    ) as response:
                        response.raise_for_status()
                        if response.status_code != 206 or response.headers.get("Content-Range") != f"bytes {start}-{end}/{total_size}":
                            raise OSError("下载服务器返回的分段范围不符")
                        with segment.open("wb") as output:
                            for chunk in response.iter_content(256 * 1024):
                                output.write(chunk)
                    if segment.stat().st_size != expected_size:
                        raise OSError("下载片段长度不完整")
                    return segment
                except (requests.RequestException, OSError):
                    segment.unlink(missing_ok=True)
                    if attempt == 3:
                        raise
                    time.sleep(attempt + 1)

        with ThreadPoolExecutor(max_workers=4) as executor:
            completed = list(executor.map(download_segment, range(0, total_size, segment_size)))
        with temporary.open("wb") as output:
            for segment in completed:
                with segment.open("rb") as source:
                    shutil.copyfileobj(source, output)
        if temporary.stat().st_size != total_size:
            raise OSError("下载文件长度不完整")
        temporary.replace(destination)
        shutil.rmtree(segments)
    except Exception as exc:
        raise DownloadError(
            f"下载媒体文件失败：{exc}",
            {"bucket": settings["R2_BUCKET"], "key": key, "destination_path": str(destination)},
        ) from exc
    return {
        "path": str(destination),
        "key": key,
        "bucket": settings["R2_BUCKET"],
        "size": destination.stat().st_size,
    }


def delete_public_file(object_key: str) -> dict:
    """删除成片或图片；文件不存在也视为成功。"""
    key = _normalize_key(object_key)
    settings = _settings()
    client = _client(settings["R2_ACCOUNT_ID"], settings["R2_ACCESS_KEY_ID"], settings["R2_SECRET_ACCESS_KEY"])
    try:
        client.delete_object(Bucket=settings["R2_BUCKET"], Key=key)
    except Exception as exc:
        raise UploadError(
            f"删除媒体文件失败：{exc}",
            {"bucket": settings["R2_BUCKET"], "key": key},
        ) from exc
    return {"deleted": True, "key": key, "bucket": settings["R2_BUCKET"]}


def delete_public_files(object_keys: list[str | Path]) -> dict:
    """批量删除成片或图片；文件不存在也视为成功。"""
    keys = list(dict.fromkeys(_normalize_key(str(item)) for item in object_keys))
    if not keys:
        raise InvalidParameterError("object_keys 至少需要包含一个对象路径", {"parameter": "object_keys"})
    if len(keys) > 1000:
        raise InvalidParameterError("object_keys 单次最多删除 1000 个对象", {"parameter": "object_keys"})
    settings = _settings()
    client = _client(settings["R2_ACCOUNT_ID"], settings["R2_ACCESS_KEY_ID"], settings["R2_SECRET_ACCESS_KEY"])
    try:
        response = client.delete_objects(
            Bucket=settings["R2_BUCKET"],
            Delete={"Objects": [{"Key": key} for key in keys], "Quiet": True},
        )
    except Exception as exc:
        raise UploadError(
            f"批量删除媒体文件失败：{exc}",
            {"bucket": settings["R2_BUCKET"], "count": len(keys)},
        ) from exc
    errors = response.get("Errors") or []
    if errors:
        raise UploadError(
            "批量删除媒体文件时部分文件失败",
            {"bucket": settings["R2_BUCKET"], "errors": errors},
        )
    return {"deleted": True, "keys": keys, "bucket": settings["R2_BUCKET"]}
