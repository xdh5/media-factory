"""生图工具内部画风选择实现，不作为独立 Tool 暴露。"""

from __future__ import annotations

from pathlib import Path

from ._constants import SUPPORTED_STYLE_IDS, VISUAL_STYLE_LIBRARY
from ._errors import InvalidParameterError, ReferenceImageError, StyleNotFoundError


def _select_style(style: str) -> dict:
    if not isinstance(style, str) or not style.strip():
        raise InvalidParameterError("style", "style 必须是非空字符串")
    normalized = style.strip().lower()
    if normalized not in SUPPORTED_STYLE_IDS:
        raise StyleNotFoundError(normalized)
    selected = next(item for item in VISUAL_STYLE_LIBRARY if item["id"] == normalized)
    reference = Path(selected["reference_image_path"])
    if not reference.is_file():
        raise ReferenceImageError(
            f"画风 '{normalized}' 的参考图不存在：{reference}",
            {"style": normalized, "reference_image_path": str(reference)},
        )
    return dict(selected)
