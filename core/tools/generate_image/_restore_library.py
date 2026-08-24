"""本地图库缺失时，从 Cloudflare R2 缓存包恢复。"""

from __future__ import annotations

import shutil
import tarfile
import tempfile
from dataclasses import dataclass
from pathlib import Path, PurePosixPath

from core.tools.r2_storage import R2StorageError, download_public_file

from ._constants import (
    FINANCE_GENERATED_LIBRARY_ARCHIVE_KEY,
    FINANCE_GENERATED_LIBRARY_ARCHIVE_NAME,
    FINANCE_GENERATED_LIBRARY_LINE,
    FINANCE_GENERATED_LIBRARY_ROOT,
    FINANCE_LEGACY_LIBRARY_ARCHIVE_KEY,
    FINANCE_LEGACY_LIBRARY_ARCHIVE_NAME,
    FINANCE_LEGACY_LIBRARY_LINE,
    FINANCE_LEGACY_LIBRARY_ROOT,
    FINANCE_LOCAL_LIBRARY_LINES,
    IMAGE_LIBRARY_CACHE_ROOT,
)
from ._errors import ImageLibraryDataError


@dataclass(frozen=True)
class FinanceLibrarySpec:
    line: str
    local_root: Path
    archive_name: str
    archive_key: str
    extract_candidates: tuple[str, ...]


FINANCE_LIBRARY_SPECS: dict[str, FinanceLibrarySpec] = {
    FINANCE_LEGACY_LIBRARY_LINE: FinanceLibrarySpec(
        line=FINANCE_LEGACY_LIBRARY_LINE,
        local_root=FINANCE_LEGACY_LIBRARY_ROOT,
        archive_name=FINANCE_LEGACY_LIBRARY_ARCHIVE_NAME,
        archive_key=FINANCE_LEGACY_LIBRARY_ARCHIVE_KEY,
        extract_candidates=(
            "data/image_library/finance",
            "image_library/finance",
        ),
    ),
    FINANCE_GENERATED_LIBRARY_LINE: FinanceLibrarySpec(
        line=FINANCE_GENERATED_LIBRARY_LINE,
        local_root=FINANCE_GENERATED_LIBRARY_ROOT,
        archive_name=FINANCE_GENERATED_LIBRARY_ARCHIVE_NAME,
        archive_key=FINANCE_GENERATED_LIBRARY_ARCHIVE_KEY,
        extract_candidates=(
            "data/image_library_finance",
            "image_library_finance",
        ),
    ),
}


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


def _resolve_spec(line: str) -> FinanceLibrarySpec:
    normalized = str(line or "").strip()
    spec = FINANCE_LIBRARY_SPECS.get(normalized)
    if spec is None:
        raise ImageLibraryDataError(
            f"不支持的财经图库 line：{normalized or '(空)'}",
            {"supported_lines": list(FINANCE_LOCAL_LIBRARY_LINES)},
        )
    return spec


def restore_image_library(line: str) -> Path:
    """指定财经图库存在时直接返回；缺失时下载并安全解压 R2 缓存包。"""
    spec = _resolve_spec(line)
    expected = spec.local_root
    if _has_files(expected):
        return expected
    archive = IMAGE_LIBRARY_CACHE_ROOT / spec.archive_name
    if not archive.is_file() or archive.stat().st_size == 0:
        try:
            download_public_file(spec.archive_key, archive)
        except R2StorageError as exc:
            raise ImageLibraryDataError(
                f"本地 {spec.line} 图库不存在，且无法从 Cloudflare R2 恢复：{exc.message}",
                exc.details,
            ) from exc
    IMAGE_LIBRARY_CACHE_ROOT.mkdir(parents=True, exist_ok=True)
    with tempfile.TemporaryDirectory(prefix=f"{spec.line}-library-", dir=IMAGE_LIBRARY_CACHE_ROOT) as temporary:
        staging = Path(temporary)
        try:
            with tarfile.open(archive, "r:") as bundle:
                bundle.extractall(staging, members=_validated_members(bundle))
        except (tarfile.TarError, OSError) as exc:
            raise ImageLibraryDataError(f"解压 R2 图库失败：{archive}。{exc}") from exc
        source = next(
            (
                staging.joinpath(*PurePosixPath(candidate).parts)
                for candidate in spec.extract_candidates
                if _has_files(staging.joinpath(*PurePosixPath(candidate).parts))
            ),
            None,
        )
        if source is None:
            raise ImageLibraryDataError(
                f"R2 图库解压后找不到 {spec.line} 图片目录",
                {"archive": str(archive), "candidates": list(spec.extract_candidates)},
            )
        expected.parent.mkdir(parents=True, exist_ok=True)
        if expected.exists() and not _has_files(expected):
            shutil.rmtree(expected)
        if expected.exists():
            raise ImageLibraryDataError(f"本地图库目录存在但不完整，拒绝覆盖：{expected}")
        shutil.move(str(source), str(expected))
    if not _has_files(expected):
        raise ImageLibraryDataError(f"从 R2 恢复后图库仍为空：{expected}")
    return expected
