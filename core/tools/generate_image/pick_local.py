"""从 Cloudflare D1 读取图库目录，本地缺图时从 R2 恢复，供宿主 Agent 选图。"""

from __future__ import annotations

import random
from pathlib import Path

from core.tools.cloudflare_data import (
    CloudflareDataError,
    list_finance_generated_images,
    list_image_library,
)

from ._constants import (
    FINANCE_GENERATED_LIBRARY_LINE,
    FINANCE_LEGACY_LIBRARY_LINE,
    FINANCE_LOCAL_LIBRARY_LINES,
    IMAGE_LIBRARY_PROJECT_ROOT,
)
from ._errors import ImageLibraryDataError, ImageLibraryEmptyError, InvalidParameterError
from ._restore_library import restore_image_library

__all__ = ["choose_finance_library_line", "list_local_images"]


def choose_finance_library_line() -> str:
    """每期随机固定一个财经本地图库；整期所有镜头必须来自同一图库。"""
    return random.choice(list(FINANCE_LOCAL_LIBRARY_LINES))


def _validate_line(line: str) -> str:
    value = str(line or "").strip()
    if value not in FINANCE_LOCAL_LIBRARY_LINES:
        raise InvalidParameterError(
            "line",
            f"财经本地图库 line 只能是 {', '.join(FINANCE_LOCAL_LIBRARY_LINES)}",
        )
    return value


def _resolve_image(image_path: str | None) -> Path | None:
    raw = str(image_path or "").strip()
    if not raw:
        return None
    path = Path(raw)
    if not path.is_absolute():
        path = IMAGE_LIBRARY_PROJECT_ROOT / path
    path = path.resolve()
    return path if path.is_file() else None


def _list_catalog_rows(line: str) -> list[dict]:
    if line == FINANCE_GENERATED_LIBRARY_LINE:
        return list_finance_generated_images()
    if line == FINANCE_LEGACY_LIBRARY_LINE:
        return list_image_library(line=FINANCE_LEGACY_LIBRARY_LINE)
    raise InvalidParameterError("line", f"未实现的财经图库 line：{line}")


def list_local_images(line: str) -> list[dict]:
    """确保本地图片已从 R2 恢复，再结合对应 D1 表返回图库。"""
    workflow = _validate_line(line)
    restore_image_library(workflow)
    try:
        rows = _list_catalog_rows(workflow)
    except CloudflareDataError as exc:
        raise ImageLibraryDataError(
            f"读取 Cloudflare D1 图库失败：{exc.message}",
            exc.details,
        ) from exc
    catalog: list[dict] = []
    for row in rows:
        source = _resolve_image(row.get("image_path"))
        if source is None:
            continue
        catalog.append(
            {
                "id": int(row["id"]),
                "caption": str(row.get("caption") or ""),
                "image_path": str(row.get("image_path") or "").strip(),
            }
        )
    if not catalog:
        raise ImageLibraryEmptyError(
            f"业务线 {workflow} 的 D1 图库为空，或当前机器尚未从 R2 恢复图片文件。",
            {"line": workflow},
        )
    return catalog
