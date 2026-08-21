"""字幕样式与位置解析：全局默认 + 逐句覆盖。"""

from __future__ import annotations

import hashlib
import json
import re
from copy import deepcopy

from ._constants import (
    SUBTITLE_CANVAS_WIDTH_RATIO,
    SUBTITLE_DEFAULT_COLORS,
    SUBTITLE_DEFAULT_FONT_SIZE,
    SUBTITLE_MAX_LINES,
    SUBTITLE_STYLES,
    SUPPORTED_SUBTITLE_ALIGNMENTS,
    SUPPORTED_SUBTITLE_LANGUAGES,
)
from ._errors import InvalidParameterError, UnsupportedSubtitleLanguageError

_POSITION_KEYS = frozenset({
    "alignment",
    "margin_left",
    "margin_right",
    "margin_vertical",
    "margin_left_ratio",
    "margin_right_ratio",
    "margin_vertical_ratio",
    "x",
    "y",
})

_STYLE_KEYS = frozenset({
    "font",
    "font_size",
    "font_size_ratio",
    "primary_color",
    "secondary_color",
    "outline_color",
    "back_color",
    "outline",
    "outline_ratio",
    "shadow",
    "shadow_ratio",
    "bold",
    "italic",
    "max_lines",
    "canvas_width_ratio",
})
INLINE_STYLE_KEYS = _STYLE_KEYS - {"max_lines", "canvas_width_ratio"}


def _validate_options(options: dict | None, parameter: str, allowed: frozenset[str]) -> dict:
    if options is None:
        return {}
    if not isinstance(options, dict):
        raise InvalidParameterError(parameter, f"{parameter} 必须是对象")
    unknown = sorted(set(options) - allowed)
    if unknown:
        raise InvalidParameterError(parameter, f"{parameter} 含未知字段：{unknown}")
    return options


def _parse_color(value: str, parameter: str) -> str:
    raw = str(value or "").strip()
    if not raw:
        raise InvalidParameterError(parameter, f"{parameter} 不能为空")
    if raw.upper().startswith("&H"):
        return raw
    cleaned = raw.lstrip("#")
    if not re.fullmatch(r"[0-9A-Fa-f]{6}", cleaned):
        raise InvalidParameterError(
            parameter,
            f"{parameter} 必须是 #RRGGBB、RRGGBB 或 ASS &H 格式，收到 {value!r}",
        )
    red, green, blue = cleaned[0:2], cleaned[2:4], cleaned[4:6]
    return f"&H00{blue.upper()}{green.upper()}{red.upper()}"


def _pick_number(
    layers: list[dict],
    key: str,
    *,
    parameter: str,
    minimum: float | None = None,
    maximum: float | None = None,
) -> float | None:
    for layer in reversed(layers):
        if key not in layer:
            continue
        value = layer[key]
        if not isinstance(value, (int, float)):
            raise InvalidParameterError(parameter, f"{key} 必须是数字")
        if minimum is not None and value < minimum:
            raise InvalidParameterError(parameter, f"{key} 不能小于 {minimum}")
        if maximum is not None and value > maximum:
            raise InvalidParameterError(parameter, f"{key} 不能大于 {maximum}")
        return float(value)
    return None


def _pick_bool(layers: list[dict], key: str, *, parameter: str) -> bool | None:
    for layer in reversed(layers):
        if key not in layer:
            continue
        value = layer[key]
        if not isinstance(value, bool):
            raise InvalidParameterError(parameter, f"{key} 必须是布尔值")
        return value
    return None


def _pick_string(layers: list[dict], key: str, *, parameter: str) -> str | None:
    for layer in reversed(layers):
        if key not in layer:
            continue
        value = str(layer[key] or "").strip()
        if not value:
            raise InvalidParameterError(parameter, f"{key} 不能为空字符串")
        return value
    return None


def _style_fingerprint(resolved: dict) -> str:
    payload = {
        key: resolved[key]
        for key in (
            "font", "font_size", "primary_color", "secondary_color", "outline_color", "back_color",
            "outline", "shadow", "bold", "italic", "alignment",
            "margin_left", "margin_right", "margin_vertical",
        )
    }
    digest = hashlib.sha1(json.dumps(payload, sort_keys=True, ensure_ascii=False).encode("utf-8")).hexdigest()
    return digest[:10]


def resolve_subtitle_style(
    language: str,
    width: int,
    height: int,
    *,
    style: dict | None = None,
    position: dict | None = None,
    style_parameter: str = "style",
    position_parameter: str = "position",
) -> dict:
    """合并语言默认、全局与逐句覆盖，返回 ASS 所需字段。"""
    normalized_language = str(language or "").strip().lower()
    if normalized_language not in SUBTITLE_STYLES:
        raise UnsupportedSubtitleLanguageError(normalized_language, SUPPORTED_SUBTITLE_LANGUAGES)

    style_layers = [
        deepcopy(SUBTITLE_STYLES[normalized_language]),
        _validate_options(style, style_parameter, _STYLE_KEYS),
    ]
    position_layers = [_validate_options(position, position_parameter, _POSITION_KEYS)]

    font = _pick_string(style_layers, "font", parameter=style_parameter) or SUBTITLE_STYLES[normalized_language]["font"]

    font_size = _pick_number(style_layers, "font_size", parameter=style_parameter, minimum=8)
    if font_size is None:
        ratio = _pick_number(style_layers, "font_size_ratio", parameter=style_parameter, minimum=0, maximum=1)
        if ratio is not None:
            font_size = max(8, round(height * ratio))
        else:
            font_size = SUBTITLE_DEFAULT_FONT_SIZE

    outline = _pick_number(style_layers, "outline", parameter=style_parameter, minimum=0)
    if outline is None:
        outline_ratio = _pick_number(style_layers, "outline_ratio", parameter=style_parameter, minimum=0, maximum=1)
        if outline_ratio is None:
            outline_ratio = SUBTITLE_STYLES[normalized_language]["outline_ratio"]
        outline = max(0, round(height * outline_ratio))

    shadow = _pick_number(style_layers, "shadow", parameter=style_parameter, minimum=0)
    if shadow is None:
        shadow_ratio = _pick_number(style_layers, "shadow_ratio", parameter=style_parameter, minimum=0, maximum=1)
        if shadow_ratio is None:
            shadow_ratio = SUBTITLE_STYLES[normalized_language]["shadow_ratio"]
        shadow = max(0, round(height * shadow_ratio))

    canvas_width_ratio = _pick_number(
        style_layers, "canvas_width_ratio", parameter=style_parameter, minimum=0.1, maximum=1,
    )
    if canvas_width_ratio is None:
        canvas_width_ratio = SUBTITLE_CANVAS_WIDTH_RATIO

    max_lines = _pick_number(style_layers, "max_lines", parameter=style_parameter, minimum=1, maximum=4)
    if max_lines is None:
        max_lines = SUBTITLE_MAX_LINES
    max_lines = int(max_lines)

    bold = _pick_bool(style_layers, "bold", parameter=style_parameter)
    if bold is None:
        bold = False
    italic = _pick_bool(style_layers, "italic", parameter=style_parameter)

    primary_color = SUBTITLE_DEFAULT_COLORS["primary_color"]
    secondary_color = SUBTITLE_DEFAULT_COLORS["secondary_color"]
    outline_color = SUBTITLE_DEFAULT_COLORS["outline_color"]
    back_color = SUBTITLE_DEFAULT_COLORS["back_color"]
    for layer in style_layers:
        for key in ("primary_color", "secondary_color", "outline_color", "back_color"):
            if key in layer:
                parsed = _parse_color(str(layer[key]), f"{style_parameter}.{key}")
                if key == "primary_color":
                    primary_color = parsed
                elif key == "secondary_color":
                    secondary_color = parsed
                elif key == "outline_color":
                    outline_color = parsed
                else:
                    back_color = parsed

    alignment = _pick_number(
        position_layers, "alignment", parameter=position_parameter,
        minimum=min(SUPPORTED_SUBTITLE_ALIGNMENTS), maximum=max(SUPPORTED_SUBTITLE_ALIGNMENTS),
    )
    if alignment is None:
        alignment = SUBTITLE_STYLES[normalized_language]["alignment"]
    alignment = int(alignment)

    margin_left = _pick_number(position_layers, "margin_left", parameter=position_parameter, minimum=0)
    if margin_left is None:
        ratio = _pick_number(position_layers, "margin_left_ratio", parameter=position_parameter, minimum=0, maximum=1)
        if ratio is None:
            margin_left = max(0, round(width * (1 - canvas_width_ratio) / 2))
        else:
            margin_left = max(0, round(width * ratio))

    margin_right = _pick_number(position_layers, "margin_right", parameter=position_parameter, minimum=0)
    if margin_right is None:
        ratio = _pick_number(position_layers, "margin_right_ratio", parameter=position_parameter, minimum=0, maximum=1)
        if ratio is None:
            margin_right = max(0, round(width * (1 - canvas_width_ratio) / 2))
        else:
            margin_right = max(0, round(width * ratio))

    margin_vertical = _pick_number(position_layers, "margin_vertical", parameter=position_parameter, minimum=0)
    if margin_vertical is None:
        ratio = _pick_number(
            position_layers, "margin_vertical_ratio", parameter=position_parameter, minimum=0, maximum=1,
        )
        if ratio is None:
            ratio = SUBTITLE_STYLES[normalized_language]["margin_vertical_ratio"]
        margin_vertical = max(0, round(height * ratio))

    pos_x = _pick_number(position_layers, "x", parameter=position_parameter, minimum=0)
    pos_y = _pick_number(position_layers, "y", parameter=position_parameter, minimum=0)
    pos = None
    if pos_x is not None or pos_y is not None:
        if pos_x is None or pos_y is None:
            raise InvalidParameterError(position_parameter, "position.x 与 position.y 必须同时提供")
        pos = (int(pos_x), int(pos_y))

    available_width = max(1, width - int(margin_left) - int(margin_right))
    logical_max_width = max(1, round(available_width * 2 / font_size))

    resolved = {
        "language": normalized_language,
        "font": font,
        "font_size": int(font_size),
        "primary_color": primary_color,
        "secondary_color": secondary_color,
        "outline_color": outline_color,
        "back_color": back_color,
        "outline": int(outline),
        "shadow": int(shadow),
        "bold": bool(bold),
        "italic": bool(italic),
        "alignment": alignment,
        "margin_left": int(margin_left),
        "margin_right": int(margin_right),
        "margin_vertical": int(margin_vertical),
        "max_lines": max_lines,
        "max_width": logical_max_width,
        "canvas_width": width,
        "canvas_height": height,
        "pos": pos,
        "style_name": "",
    }
    resolved["style_name"] = f"S_{_style_fingerprint(resolved)}"
    return resolved


def build_inline_markup(base: dict, span: dict) -> tuple[str, str]:
    """相对 cue 基础样式生成 ASS 行内开关标签。"""
    tags: list[str] = []
    if span["font"] != base["font"]:
        tags.append(rf"\fn{span['font']}")
    if span["font_size"] != base["font_size"]:
        tags.append(rf"\fs{span['font_size']}")
    if span["primary_color"] != base["primary_color"]:
        tags.append(rf"\1c{span['primary_color']}&")
    if span["outline_color"] != base["outline_color"]:
        tags.append(rf"\3c{span['outline_color']}&")
    if span["back_color"] != base["back_color"]:
        tags.append(rf"\4c{span['back_color']}&")
    if span["bold"] != base["bold"]:
        tags.append(rf"\b{1 if span['bold'] else 0}")
    if span["italic"] != base["italic"]:
        tags.append(rf"\i{1 if span['italic'] else 0}")
    if span["outline"] != base["outline"]:
        tags.append(rf"\bord{span['outline']}")
    if span["shadow"] != base["shadow"]:
        tags.append(rf"\shad{span['shadow']}")
    if not tags:
        return "", ""
    return "{" + "".join(tags) + "}", r"{\r}"
