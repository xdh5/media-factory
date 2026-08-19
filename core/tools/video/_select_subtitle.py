"""按语言选择字幕样式。"""

from __future__ import annotations

from copy import deepcopy
import re

from ._constants import SUBTITLE_CANVAS_WIDTH_RATIO, SUBTITLE_STYLES, SUPPORTED_SUBTITLE_LANGUAGES
from ._errors import InvalidParameterError, UnsupportedSubtitleLanguageError


def _parse_size(size: str) -> tuple[int, int]:
    matched = re.fullmatch(r"\s*(\d+)\s*[xX×]\s*(\d+)\s*", str(size or ""))
    if not matched:
        raise InvalidParameterError("size", "size 必须使用 WIDTHxHEIGHT 格式，例如 1920x1080")
    width, height = (int(value) for value in matched.groups())
    if width < 2 or height < 2 or width % 2 or height % 2:
        raise InvalidParameterError("size", "宽高必须是大于等于 2 的偶数，以兼容 H.264 yuv420p 输出")
    return width, height


def _select_subtitle(language: str, size: str) -> dict:
    """按目标画布尺寸返回字体、字号、位置和换行配置，仅供镜头渲染内部使用。"""
    normalized = str(language or "").strip().lower()
    if normalized not in SUBTITLE_STYLES:
        raise UnsupportedSubtitleLanguageError(normalized, SUPPORTED_SUBTITLE_LANGUAGES)
    width, height = _parse_size(size)
    style = deepcopy(SUBTITLE_STYLES[normalized])
    font_size = max(1, round(height * style.pop("font_size_ratio")))
    horizontal_margin = max(0, round(width * (1 - SUBTITLE_CANVAS_WIDTH_RATIO) / 2))
    available_width = max(1, width - horizontal_margin * 2)
    # _wrap_text 中一个全角字符按 2 个逻辑单位计算，据实际可用像素宽度换算阈值。
    logical_max_width = max(1, round(available_width * 2 / font_size))
    style.update({
        "canvas_width": width,
        "canvas_height": height,
        "font_size": font_size,
        "margin_left": horizontal_margin,
        "margin_right": horizontal_margin,
        "margin_vertical": max(0, round(height * style.pop("margin_vertical_ratio"))),
        "max_width": logical_max_width,
        "outline": max(0, round(height * style.pop("outline_ratio"))),
        "shadow": max(0, round(height * style.pop("shadow_ratio"))),
    })
    return style
