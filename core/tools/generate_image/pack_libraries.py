"""打包财经本地图库并上传到 R2。"""

from __future__ import annotations

import tarfile
from pathlib import Path

from core.tools.r2_storage import upload_public_file

from ._constants import (
    FINANCE_GENERATED_LIBRARY_ARCHIVE_KEY,
    FINANCE_GENERATED_LIBRARY_ARCHIVE_NAME,
    FINANCE_GENERATED_LIBRARY_ROOT,
    FINANCE_LEGACY_LIBRARY_ARCHIVE_KEY,
    FINANCE_LEGACY_LIBRARY_ARCHIVE_NAME,
    FINANCE_LEGACY_LIBRARY_PACK_ROOT,
    IMAGE_LIBRARY_CACHE_ROOT,
)

__all__ = ["pack_finance_libraries", "upload_finance_libraries"]


def _has_png_files(directory: Path) -> bool:
    return directory.is_dir() and any(directory.rglob("*.png"))


def _pack_directory(source_dir: Path, archive_path: Path, *, arcname: str) -> dict:
    if not _has_png_files(source_dir):
        raise ValueError(f"图库目录不存在或没有 PNG 文件：{source_dir}")
    archive_path.parent.mkdir(parents=True, exist_ok=True)
    with tarfile.open(archive_path, "w:") as bundle:
        bundle.add(source_dir, arcname=arcname)
    return {
        "source_dir": str(source_dir),
        "archive_path": str(archive_path),
        "size_bytes": archive_path.stat().st_size,
    }


def pack_finance_libraries() -> dict:
    """把两个财经图库目录分别打成 tar。"""
    legacy_archive = IMAGE_LIBRARY_CACHE_ROOT / FINANCE_LEGACY_LIBRARY_ARCHIVE_NAME
    generated_archive = IMAGE_LIBRARY_CACHE_ROOT / FINANCE_GENERATED_LIBRARY_ARCHIVE_NAME
    return {
        "finance": _pack_directory(
            FINANCE_LEGACY_LIBRARY_PACK_ROOT,
            legacy_archive,
            arcname="data/image_library",
        ),
        "finance_generated": _pack_directory(
            FINANCE_GENERATED_LIBRARY_ROOT,
            generated_archive,
            arcname="data/image_library_finance",
        ),
    }


def upload_finance_libraries() -> dict:
    """打包并上传两个财经图库 tar 到 R2。"""
    packed = pack_finance_libraries()
    uploaded = {
        "finance": upload_public_file(
            packed["finance"]["archive_path"],
            FINANCE_LEGACY_LIBRARY_ARCHIVE_KEY,
            content_type="application/x-tar",
        ),
        "finance_generated": upload_public_file(
            packed["finance_generated"]["archive_path"],
            FINANCE_GENERATED_LIBRARY_ARCHIVE_KEY,
            content_type="application/x-tar",
        ),
    }
    return {"packed": packed, "uploaded": uploaded}
