"""ASS 字幕时间轴生成。"""

from __future__ import annotations

from pathlib import Path
from functools import lru_cache
from PIL import ImageFont
from fontTools.ttLib import TTFont
from ._constants import SUBTITLE_FONT_DIRECTORY

from ._errors import InvalidParameterError
from ._style import resolve_subtitle_style
from ._text import build_rich_ass_text, parse_cue_text, wrap_plain_text
from ._words import build_word_events, build_word_units


def _ass_time(seconds: float) -> str:
    centiseconds = max(0, round(seconds * 100))
    hours, centiseconds = divmod(centiseconds, 360_000)
    minutes, centiseconds = divmod(centiseconds, 6_000)
    secs, centiseconds = divmod(centiseconds, 100)
    return f"{hours}:{minutes:02d}:{secs:02d}.{centiseconds:02d}"


def _escape_ass_text(value: str) -> str:
    return value.replace("\\", r"\\").replace("{", "（").replace("}", "）")


@lru_cache(maxsize=16)
def _background_font(name: str, size: int):
    """匹配字幕字体，并换算 libass 使用的字号尺度。"""
    for path in SUBTITLE_FONT_DIRECTORY.iterdir():
        if path.suffix.lower() not in {'.ttf', '.otf'}:
            continue
        with TTFont(path) as font:
            names = {record.toUnicode().lower() for record in font['name'].names if record.nameID in (1, 4, 6, 16)}
            if name.lower() not in names:
                continue
            scale = font['head'].unitsPerEm / (font['hhea'].ascent - font['hhea'].descent)
        return ImageFont.truetype(str(path), size), scale
    raise InvalidParameterError('font', f'找不到字幕字体：{name}')


def _rounded_background(text: str, style: dict, width: int, height: int) -> str:
    """整块灰底：左右留白 24px、上下 14px、圆角 7px。"""
    font, scale = _background_font(style['font'], style['font_size'])
    w = round(font.getlength(text) * scale + max(0, len(text) - 1) * (style['letter_spacing'] or 0) + 48)
    h = style['font_size'] + 28
    r = 7
    k = round(r * 0.5523, 2)
    shape = (f'm {r} 0 l {w-r} 0 b {w-r+k} 0 {w} {r-k} {w} {r} '
             f'l {w} {h-r} b {w} {h-r+k} {w-r+k} {h} {w-r} {h} '
             f'l {r} {h} b {r-k} {h} 0 {h-r+k} 0 {h-r} '
             f'l 0 {r} b 0 {r-k} {r-k} 0 {r} 0')
    x, y = style['pos'] or (width // 2, height - style['margin_vertical'])
    color = style['outline_color']
    return (rf'{{\an2\pos({x},{y+14})\p1\bord0\shad0\fscx100\fscy100'
            rf'\1c&H{color[4:]}&\1a&H{color[2:4]}&}}{shape}')


def _style_line(name: str, style: dict) -> str:
    return (
        f"Style: {name},{style['font']},{style['font_size']},"
        f"{style['primary_color']},{style['secondary_color']},"
        f"{style['outline_color']},{style['back_color']},"
        f"{1 if style['bold'] else 0},{1 if style['italic'] else 0},0,0,100,100,0,0,{style['border_style']},"
        f"{style['outline']},{style['shadow']},{style['alignment']},"
        f"{style['margin_left']},{style['margin_right']},{style['margin_vertical']},1"
    )


def write_timeline_ass(
    path: Path,
    cues: list[dict],
    width: int,
    height: int,
    *,
    style: dict | None = None,
    position: dict | None = None,
) -> None:
    """按整片时间轴写出 ASS。"""
    if not cues:
        raise InvalidParameterError("cues", "没有可写入的字幕")

    resolved_styles: dict[str, dict] = {}
    events: list[str] = []
    canvas = None

    for index, cue in enumerate(cues):
        spans = parse_cue_text(cue.get("text"), parameter=f"cues[{index}].text")
        if not spans:
            continue
        language = str(cue.get("language") or "zh")
        cue_style = _merge_dict(style, cue.get("style"))
        cue_position = _merge_dict(position, cue.get("position"))
        resolved = resolve_subtitle_style(
            language,
            width,
            height,
            style=cue_style,
            position=cue_position,
            style_parameter=f"cues[{index}].style",
            position_parameter=f"cues[{index}].position",
        )
        if canvas is None:
            canvas = resolved
        if resolved["border_style"] == 3:
            background = {**resolved, "style_name": resolved["style_name"] + "_background"}
            resolved_styles[background["style_name"]] = background
            plain = _rounded_background(''.join(span['text'] for span in spans), resolved, width, height)
            events.append(f"Dialogue: 0,{_ass_time(float(cue['start']))},{_ass_time(float(cue['end']))},"
                          f"{background['style_name']},,0,0,0,,{plain}")
            resolved = {**resolved, "border_style": 1, "outline": 1, "outline_color": "&H00000000"}
        resolved_styles[resolved["style_name"]] = resolved

        use_word_events = bool(resolved.get("animation")) and isinstance(cue.get("text"), str)

        if use_word_events:
            units = build_word_units(cue, parameter=f"cues[{index}]")
            word_events = build_word_events(units, resolved, language)
            for event_start, event_end, body in word_events:
                text = body
                if resolved["pos"] is not None:
                    pos_x, pos_y = resolved["pos"]
                    text = rf"{{\pos({pos_x},{pos_y})}}{text}"
                events.append(
                    f"Dialogue: 1,{_ass_time(event_start)},{_ass_time(event_end)},"
                    f"{resolved['style_name']},,0,0,0,,{text}"
                )
            if word_events:
                continue

        has_inline_style = any(span.get("style") for span in spans)
        if has_inline_style or isinstance(cue.get("text"), list):
            # 富文本按各段字号预先均衡换行，避免放大重点词后由 libass 产生单字孤行。
            safe_text = build_rich_ass_text(
                spans,
                base_style=resolved,
                language=language,
                width=width,
                height=height,
                global_style=style,
                cue_style=cue.get("style"),
                global_position=position,
                cue_position=cue.get("position"),
                parameter=f"cues[{index}].text",
            )
        else:
            plain = str(spans[0]["text"])
            safe_text = wrap_plain_text(
                    _escape_ass_text(plain),
                    max_width=resolved["max_width"],
                    max_lines=resolved["max_lines"],
                )

        if resolved["pos"] is not None:
            pos_x, pos_y = resolved["pos"]
            safe_text = rf"{{\pos({pos_x},{pos_y})}}{safe_text}"
        events.append(
            f"Dialogue: 1,{_ass_time(float(cue['start']))},{_ass_time(float(cue['end']))},"
            f"{resolved['style_name']},,0,0,0,,{safe_text}"
        )

    if canvas is None or not events:
        raise InvalidParameterError("cues", "没有可写入的字幕文本")

    style_lines = [_style_line(name, resolved) for name, resolved in sorted(resolved_styles.items())]
    header = f"""[Script Info]
ScriptType: v4.00+
PlayResX: {canvas['canvas_width']}
PlayResY: {canvas['canvas_height']}
WrapStyle: 0
ScaledBorderAndShadow: yes

[V4+ Styles]
Format: Name, Fontname, Fontsize, PrimaryColour, SecondaryColour, OutlineColour, BackColour, Bold, Italic, Underline, StrikeOut, ScaleX, ScaleY, Spacing, Angle, BorderStyle, Outline, Shadow, Alignment, MarginL, MarginR, MarginV, Encoding
{chr(10).join(style_lines)}

[Events]
Format: Layer, Start, End, Style, Name, MarginL, MarginR, MarginV, Effect, Text
{chr(10).join(events)}
"""
    path.write_text(header, encoding="utf-8")


def _merge_dict(base: dict | None, override: dict | None) -> dict | None:
    if base is None and override is None:
        return None
    merged: dict = dict(base or {})
    if override:
        merged.update(override)
    return merged
