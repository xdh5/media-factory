"""重点句大字图层的版式与 ASS 输出。"""

from __future__ import annotations

import random
from pathlib import Path

from ._animations import SUPPORTED_ANIMATIONS, entrance_tags
from ._constants import (
    EMPHASIS_ANIMATION_DURATION,
    EMPHASIS_BOLD,
    EMPHASIS_CENTER_RATIO,
    EMPHASIS_FONT_FAMILY,
    EMPHASIS_FONT_SIZE,
    EMPHASIS_HIGHLIGHT_COLOR,
    EMPHASIS_LINE_HEIGHT,
    EMPHASIS_OUTLINE,
    EMPHASIS_OUTLINE_COLOR,
    EMPHASIS_PRIMARY_COLOR,
)


def _ass_time(seconds: float) -> str:
    centiseconds = max(0, round(seconds * 100))
    hours, centiseconds = divmod(centiseconds, 360_000)
    minutes, centiseconds = divmod(centiseconds, 6_000)
    secs, centiseconds = divmod(centiseconds, 100)
    return f"{hours}:{minutes:02d}:{secs:02d}.{centiseconds:02d}"


def _ass_color(rgb: str) -> str:
    """#RRGGBB → &HBBGGRR（ASS 的 BGR 口径）。"""
    value = str(rgb or "").strip().lstrip("#")
    if len(value) != 6:
        raise ValueError(f"颜色必须是 #RRGGBB：{rgb!r}")
    red, green, blue = value[0:2], value[2:4], value[4:6]
    return f"&H{blue}{green}{red}"


def _escape(text: str) -> str:
    return str(text or "").replace("{", "（").replace("}", "）")


def split_keyword_spans(text: str, keywords: list[str]) -> list[tuple[str, bool]]:
    """把行文本按重点词切成 (片段, 是否重点)；重点词按长度优先匹配。"""
    ordered = sorted({word for word in keywords if word}, key=len, reverse=True)
    spans: list[tuple[str, bool]] = []
    index = 0
    while index < len(text):
        matched = next(
            (word for word in ordered if word and text.startswith(word, index)),
            None,
        )
        if matched:
            spans.append((matched, True))
            index += len(matched)
            continue
        if spans and not spans[-1][1]:
            spans[-1] = (spans[-1][0] + text[index], False)
        else:
            spans.append((text[index], False))
        index += 1
    return spans


def _rich_line(text: str, keywords: list[str], primary: str, highlight: str) -> str:
    spans = split_keyword_spans(text, keywords)
    if not any(flag for _, flag in spans):
        return _escape(text)
    primary_tag = rf"\1c{_ass_color(primary)}"
    highlight_tag = rf"\1c{_ass_color(highlight)}"
    parts: list[str] = []
    for chunk, emphasized in spans:
        parts.append(
            f"{{{highlight_tag if emphasized else primary_tag}}}{_escape(chunk)}"
        )
    return "".join(parts)


def _style_line(name: str, settings: dict) -> str:
    return (
        f"Style: {name},{EMPHASIS_FONT_FAMILY},{int(settings['font_size'])},"
        f"{_ass_color(settings['primary_color'])},&H00FFFFFF,"
        f"{_ass_color(settings['outline_color'])},&H00000000,"
        f"{1 if settings['bold'] else 0},0,0,0,100,100,0,0,1,"
        f"{int(settings['outline'])},0,5,0,0,0,1"
    )


def _event(
    start: float,
    end: float,
    name: str,
    animation: str,
    x: int,
    y: int,
    body: str,
    duration: float,
) -> str:
    return (
        f"Dialogue: 1,{_ass_time(start)},{_ass_time(end)},{name},,0,0,0,,"
        f"{{{entrance_tags(animation, x, y, duration)}}}{body}"
    )


def write_emphasis_ass(
    path: Path,
    groups: list[list[dict]],
    width: int,
    height: int,
    settings: dict,
) -> None:
    """按组写出大字图层 ASS。

    groups 每项是一组已排好序的内容行：
    [{"text": str, "keywords": [str], "start": float, "group_end": float}]
    """
    canvas_width, canvas_height = int(width), int(height)
    font_size = int(settings["font_size"])
    line_height = round(font_size * float(settings["line_height"]))
    center_y = round(canvas_height * float(settings["center_ratio"]))
    center_x = canvas_width // 2
    animations = [name for name in settings["animations"] if name in SUPPORTED_ANIMATIONS] or [
        "slam"
    ]
    duration = float(settings.get("animation_duration") or EMPHASIS_ANIMATION_DURATION)
    rng = random.Random(settings.get("seed"))

    events: list[str] = []
    for group in groups:
        total = len(group)
        for order, line in enumerate(group):
            y = center_y + round((order - (total - 1) / 2) * line_height)
            animation = rng.choice(animations)
            body = _rich_line(
                line["text"],
                line.get("keywords") or [],
                settings["primary_color"],
                settings["highlight_color"],
            )
            events.append(
                _event(
                    float(line["start"]),
                    float(line["group_end"]),
                    "EMP",
                    animation,
                    center_x,
                    y,
                    body,
                    duration,
                )
            )
    if not events:
        raise ValueError("没有可写入的重点句大字")

    header = f"""[Script Info]
ScriptType: v4.00+
PlayResX: {canvas_width}
PlayResY: {canvas_height}
WrapStyle: 0
ScaledBorderAndShadow: yes

[V4+ Styles]
Format: Name, Fontname, Fontsize, PrimaryColour, SecondaryColour, OutlineColour, BackColour, Bold, Italic, Underline, StrikeOut, ScaleX, ScaleY, Spacing, Angle, BorderStyle, Outline, Shadow, Alignment, MarginL, MarginR, MarginV, Encoding
{_style_line('EMP', settings)}

[Events]
Format: Layer, Start, End, Style, Name, MarginL, MarginR, MarginV, Effect, Text
{chr(10).join(events)}
"""
    path.write_text(header, encoding="utf-8")


__all__ = [
    "write_emphasis_ass",
    "split_keyword_spans",
    "EMPHASIS_FONT_SIZE",
    "EMPHASIS_PRIMARY_COLOR",
    "EMPHASIS_HIGHLIGHT_COLOR",
    "EMPHASIS_OUTLINE_COLOR",
    "EMPHASIS_OUTLINE",
    "EMPHASIS_BOLD",
    "EMPHASIS_CENTER_RATIO",
    "EMPHASIS_LINE_HEIGHT",
]
