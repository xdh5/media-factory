"""从 Cloudflare D1 读取图库目录，本地缺图时从 R2 恢复，供宿主 Agent 选图。"""

from __future__ import annotations

import re
from pathlib import Path

from core.tools.cloudflare_data import CloudflareDataError, list_images

from ._constants import IMAGE_LIBRARY_LINE_PATTERN, IMAGE_LIBRARY_PROJECT_ROOT
from ._errors import ImageLibraryDataError, ImageLibraryEmptyError, InvalidParameterError
from ._restore_library import restore_image_library

__all__ = ["list_local_images"]


def _validate_line(line: str) -> str:
    value = str(line or "").strip()
    if not re.fullmatch(IMAGE_LIBRARY_LINE_PATTERN, value):
        raise InvalidParameterError("line", f"line 不合法：{line!r}")
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


def list_local_images(line: str) -> list[dict]:
    """确保本地图片已从 R2 恢复，再结合 D1 元数据返回图库。"""
    workflow = _validate_line(line)
    restore_image_library(workflow)
    try:
        rows = list_images(workflow)
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
