"""章节时间轴条的 ASS 图层生成。

视觉结构（自下而上）：
  Layer 0  横条底色（半透明深色矩形）
  Layer 1  进度色矩形（\\org 锚定左缘 + \\t(\\fscx 0→100) 随播放时间从左往右推进）
  Layer 2  段落分隔线
  Layer 3  段落标题（常显暗色）
  Layer 4  当前时段标题（高亮加粗，只在该时段内显示）
"""

from __future__ import annotations

import math
from pathlib import Path

from ._constants import DEFAULT_TIMELINE_STYLE, TIMELINE_POSITIONS
from ._errors import InvalidParameterError


def _ass_time(seconds: float) -> str:
    centiseconds = max(0, round(seconds * 100))
    hours, centiseconds = divmod(centiseconds, 360_000)
    minutes, centiseconds = divmod(centiseconds, 6_000)
    secs, centiseconds = divmod(centiseconds, 100)
    return f"{hours}:{minutes:02d}:{secs:02d}.{centiseconds:02d}"


def _ass_color(hex_color: str, opacity: float, parameter: str) -> str:
    """#RRGGBB + 不透明度(0~1) -> ASS &HAABBGGRR（AA 越小越实心）。"""
    value = str(hex_color or "").strip().lstrip("#")
    if len(value) != 6:
        raise InvalidParameterError(parameter, f"颜色必须是 #RRGGBB，当前为 {hex_color!r}")
    try:
        red = int(value[0:2], 16)
        green = int(value[2:4], 16)
        blue = int(value[4:6], 16)
    except ValueError as exc:
        raise InvalidParameterError(parameter, f"颜色必须是 #RRGGBB，当前为 {hex_color!r}") from exc
    if not 0 <= float(opacity) <= 1:
        raise InvalidParameterError(parameter, f"不透明度必须在 0~1 之间，当前为 {opacity}")
    alpha = round((1 - float(opacity)) * 255)
    return f"&H{alpha:02X}{blue:02X}{green:02X}{red:02X}"


def _escape_ass_text(value: str) -> str:
    return (
        str(value or "")
        .replace("\\", r"\\")
        .replace("{", "（")
        .replace("}", "）")
        .replace("\n", " ")
        .strip()
    )


def _style_line(
    name: str,
    *,
    primary: str,
    bold: int = 0,
    font: str,
    font_size: int,
    align: int = 5,
) -> str:
    # 矩形图层必须用 an7（左上角锚点）：libass 对 \p1 矢量图按包围盒对齐 \pos，
    # an5 会把矩形中心放到 \pos 上（1920 宽的条只剩左半截）。文字层仍用 an5 居中。
    return (
        f"Style: {name},{font},{font_size},{primary},&H00FFFFFF,&H00000000,&H00000000,"
        f"{bold},0,0,0,100,100,0,0,1,0,0,{align},0,0,0,1"
    )


def _truncate_title(title: str, max_chars: int) -> str:
    text = str(title or "").strip()
    if len(text) <= max_chars:
        return text
    return text[: max(1, max_chars - 1)] + "…"


def _rect(width: float, height: float) -> str:
    """以 \\pos 锚点为左上角的矩形绘制指令。"""
    return f"m 0 0 l {width:.0f} 0 {width:.0f} {height:.0f} 0 {height:.0f}"


def write_chapter_timeline_ass(
    path: Path,
    segments: list[dict],
    width: int,
    height: int,
    *,
    position: str = "top",
    style: dict | None = None,
) -> None:
    """按章节时间轴写出 ASS 覆盖图层。segments 每项含 start、end、title。"""
    if not segments:
        raise InvalidParameterError("segments", "至少需要一个章节段落")
    if position not in TIMELINE_POSITIONS:
        raise InvalidParameterError(
            "position", f"position 只能是 {' / '.join(TIMELINE_POSITIONS)}，当前为 {position!r}"
        )
    merged = {**DEFAULT_TIMELINE_STYLE, **(style or {})}
    font = str(merged["font"])
    font_size = max(8, int(merged["font_size"]))
    bar_height = max(16, int(merged["bar_height"]))
    margin_horizontal = max(0, int(merged["margin_horizontal"]))
    ratio = float(merged["margin_vertical_ratio"])
    if not 0 <= ratio <= 0.4:
        raise InvalidParameterError("margin_vertical_ratio", "必须是 0~0.4 之间的数字")

    bar_left = margin_horizontal
    bar_width = width - 2 * margin_horizontal
    if bar_width < width * 0.3:
        raise InvalidParameterError("margin_horizontal", "左右留白过大，横条宽度不足")
    if position == "top":
        bar_top = round(height * ratio)
    else:
        bar_top = round(height * (1 - ratio)) - bar_height
    bar_middle = bar_top + bar_height / 2

    total = max(float(item["end"]) for item in segments)
    count = len(segments)
    segment_width = bar_width / count
    title_max_chars = max(2, math.floor(segment_width * 0.92 / font_size))

    events: list[str] = []

    # Layer 0 横条底色
    events.append(
        f"Dialogue: 0,0:00:00.00,{_ass_time(total)},TLTrack,,0,0,0,,"
        f"{{\\pos({bar_left},{bar_top})\\p1}}{_rect(bar_width, bar_height)}{{\\p0}}"
    )

    # Layer 1 进度色：\org 固定在横条左缘，\fscx 从 0 线性放大到 100
    fill_ms = max(1, round(total * 1000))
    events.append(
        f"Dialogue: 0,0:00:00.00,{_ass_time(total)},TLFill,,0,0,0,,"
        f"{{\\pos({bar_left},{bar_top})\\org({bar_left + 1},{round(bar_middle)})\\fscx0"
        f"\\t(0,{fill_ms},\\fscx100)\\p1}}{_rect(bar_width, bar_height)}{{\\p0}}"
    )

    # Layer 2 分隔线
    separator_width = max(1, int(merged["separator_width"]))
    separator_height = round(bar_height * 0.6)
    separator_top = round(bar_middle - separator_height / 2)
    for index in range(1, count):
        x = round(bar_left + index * segment_width - separator_width / 2)
        events.append(
            f"Dialogue: 0,0:00:00.00,{_ass_time(total)},TLSep,,0,0,0,,"
            f"{{\\pos({x},{separator_top})\\p1}}"
            f"{_rect(separator_width, separator_height)}{{\\p0}}"
        )

    # Layer 3 常显标题 + Layer 4 当前时段高亮标题
    for index, item in enumerate(segments):
        start = float(item["start"])
        end = float(item["end"])
        if end <= start:
            raise InvalidParameterError(f"segments[{index}]", "end 必须大于 start")
        title = _escape_ass_text(_truncate_title(item["title"], title_max_chars))
        if not title:
            raise InvalidParameterError(f"segments[{index}].title", "章节标题不能为空")
        center_x = round(bar_left + (index + 0.5) * segment_width)
        events.append(
            f"Dialogue: 0,0:00:00.00,{_ass_time(total)},TLTitle,,0,0,0,,"
            f"{{\\pos({center_x},{round(bar_middle)})}}{title}"
        )
        events.append(
            f"Dialogue: 0,{_ass_time(start)},{_ass_time(end)},TLTitleActive,,0,0,0,,"
            f"{{\\pos({center_x},{round(bar_middle)})}}{title}"
        )

    style_lines = [
        _style_line(
            "TLTrack",
            primary=_ass_color(merged["track_color"], merged["track_opacity"], "track_color"),
            font=font,
            font_size=font_size,
            align=7,
        ),
        _style_line(
            "TLFill",
            primary=_ass_color(merged["progress_color"], merged["progress_opacity"], "progress_color"),
            font=font,
            font_size=font_size,
            align=7,
        ),
        _style_line(
            "TLSep",
            primary=_ass_color(merged["separator_color"], merged["separator_opacity"], "separator_color"),
            font=font,
            font_size=font_size,
            align=7,
        ),
        _style_line(
            "TLTitle",
            primary=_ass_color(merged["title_color"], 1.0, "title_color"),
            font=font,
            font_size=font_size,
        ),
        _style_line(
            "TLTitleActive",
            primary=_ass_color(merged["active_color"], 1.0, "active_color"),
            bold=1,
            font=font,
            font_size=font_size,
        ),
    ]

    header = f"""[Script Info]
ScriptType: v4.00+
PlayResX: {width}
PlayResY: {height}
WrapStyle: 0
ScaledBorderAndShadow: yes

[V4+ Styles]
Format: Name, Fontname, Fontsize, PrimaryColour, SecondaryColour, OutlineColour, BackColour, Bold, Italic, Underline, StrikeOut, ScaleX, ScaleY, Spacing, Angle, BorderStyle, Outline, Shadow, Alignment, MarginL, MarginR, MarginV, Encoding
{chr(10).join(style_lines)}

[Events]
Format: Layer, Start, End, Style, Name, MarginL, MarginR, MarginV, Effect, Text
{chr(10).join(events)}
"""
    Path(path).write_text(header, encoding="utf-8")
