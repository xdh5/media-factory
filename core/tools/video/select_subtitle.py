"""按语言选择字幕样式。"""

from __future__ import annotations

from copy import deepcopy
import re

from ._constants import BASE_VIDEO_HEIGHT, BASE_VIDEO_WIDTH, SUBTITLE_STYLES, SUPPORTED_SUBTITLE_LANGUAGES
from ._errors import InvalidParameterError, UnsupportedSubtitleLanguageError

__all__ = ["select_subtitle"]


def _parse_size(size: str) -> tuple[int, int]:
    matched = re.fullmatch(r"\s*(\d+)\s*[xX×]\s*(\d+)\s*", str(size or ""))
    if not matched:
        raise InvalidParameterError("size", "size 必须使用 WIDTHxHEIGHT 格式，例如 1920x1080")
    width, height = (int(value) for value in matched.groups())
    if width < 2 or height < 2 or width % 2 or height % 2:
        raise InvalidParameterError("size", "宽高必须是大于等于 2 的偶数，以兼容 H.264 yuv420p 输出")
    return width, height


def select_subtitle(language: str, size: str) -> dict:
    """按目标画布尺寸返回字体、字号、位置和换行配置。"""
    normalized = str(language or "").strip().lower()
    if normalized not in SUBTITLE_STYLES:
        raise UnsupportedSubtitleLanguageError(normalized, SUPPORTED_SUBTITLE_LANGUAGES)
    width, height = _parse_size(size)
    width_scale = width / BASE_VIDEO_WIDTH
    height_scale = height / BASE_VIDEO_HEIGHT
    uniform_scale = min(width_scale, height_scale)
    style = deepcopy(SUBTITLE_STYLES[normalized])
    style.update({
        "canvas_width": width,
        "canvas_height": height,
        "font_size": max(1, round(style["font_size"] * uniform_scale)),
        "margin_left": max(0, round(style["margin_left"] * width_scale)),
        "margin_right": max(0, round(style["margin_right"] * width_scale)),
        "margin_vertical": max(0, round(style["margin_vertical"] * height_scale)),
        "max_width": max(1, round(style["max_width"] * width_scale / uniform_scale)),
        "outline": max(0, round(style["outline"] * uniform_scale)),
        "shadow": max(0, round(style["shadow"] * uniform_scale)),
    })
    return style
