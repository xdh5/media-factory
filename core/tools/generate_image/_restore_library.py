"""本地图库缺失时，从 Cloudflare R2 缓存包恢复。"""

from __future__ import annotations

import shutil
import tarfile
import tempfile
from pathlib import Path, PurePosixPath

from core.tools.r2_storage import R2StorageError, download_public_file

from ._constants import (
    IMAGE_LIBRARY_ARCHIVE_KEY_TEMPLATE,
    IMAGE_LIBRARY_CACHE_ROOT,
    IMAGE_LIBRARY_DATA_ROOT,
)
from ._errors import ImageLibraryDataError


def _has_files(directory: Path) -> bool:
    return directory.is_dir() and any(path.is_file() for path in directory.rglob("*"))


def _validated_members(bundle: tarfile.TarFile) -> list[tarfile.TarInfo]:
    members: list[tarfile.TarInfo] = []
    for member in bundle.getmembers():
        normalized = PurePosixPath(member.name.replace("\\", "/"))
        if (
            normalized.is_absolute()
            or ".." in normalized.parts
            or (normalized.parts and ":" in normalized.parts[0])
            or member.issym()
            or member.islnk()
        ):
            raise ImageLibraryDataError(f"R2 图库压缩包包含不安全路径：{member.name}")
        members.append(member)
    if not members:
        raise ImageLibraryDataError("R2 图库压缩包为空")
    return members


def restore_image_library(line: str) -> Path:
    """本地图库存在时直接返回；缺失时下载并安全解压 R2 缓存包。"""
    expected = IMAGE_LIBRARY_DATA_ROOT / line
    if _has_files(expected):
        return expected
    archive = IMAGE_LIBRARY_CACHE_ROOT / f"{line}-images.tar"
    if not archive.is_file() or archive.stat().st_size == 0:
        try:
            download_public_file(
                IMAGE_LIBRARY_ARCHIVE_KEY_TEMPLATE.format(line=line),
                archive,
            )
        except R2StorageError as exc:
            raise ImageLibraryDataError(
                f"本地 {line} 图库不存在，且无法从 Cloudflare R2 恢复：{exc.message}",
                exc.details,
            ) from exc
    IMAGE_LIBRARY_CACHE_ROOT.mkdir(parents=True, exist_ok=True)
    with tempfile.TemporaryDirectory(prefix=f"{line}-library-", dir=IMAGE_LIBRARY_CACHE_ROOT) as temporary:
        staging = Path(temporary)
        try:
            with tarfile.open(archive, "r:") as bundle:
                bundle.extractall(staging, members=_validated_members(bundle))
        except (tarfile.TarError, OSError) as exc:
            raise ImageLibraryDataError(f"解压 R2 图库失败：{archive}。{exc}") from exc
        candidates = (
            staging / "data" / "image_library" / line,
            staging / "image_library" / line,
            staging / line,
        )
        source = next((candidate for candidate in candidates if _has_files(candidate)), None)
        if source is None:
            raise ImageLibraryDataError(f"R2 图库解压后找不到 {line} 图片目录")
        expected.parent.mkdir(parents=True, exist_ok=True)
        if expected.exists() and not _has_files(expected):
            shutil.rmtree(expected)
        if expected.exists():
            raise ImageLibraryDataError(f"本地图库目录存在但不完整，拒绝覆盖：{expected}")
        shutil.move(str(source), str(expected))
    if not _has_files(expected):
        raise ImageLibraryDataError(f"从 R2 恢复后图库仍为空：{expected}")
    return expected
