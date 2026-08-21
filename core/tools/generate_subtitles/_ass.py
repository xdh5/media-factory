"""ASS 字幕时间轴生成。"""

from __future__ import annotations

from pathlib import Path

from ._errors import InvalidParameterError
from ._style import resolve_subtitle_style
from ._text import build_rich_ass_text, parse_cue_text


def _ass_time(seconds: float) -> str:
    centiseconds = max(0, round(seconds * 100))
    hours, centiseconds = divmod(centiseconds, 360_000)
    minutes, centiseconds = divmod(centiseconds, 6_000)
    secs, centiseconds = divmod(centiseconds, 100)
    return f"{hours}:{minutes:02d}:{secs:02d}.{centiseconds:02d}"


def _escape_ass_text(value: str) -> str:
    return value.replace("\\", r"\\").replace("{", "（").replace("}", "）")


def _style_line(name: str, style: dict) -> str:
    return (
        f"Style: {name},{style['font']},{style['font_size']},"
        f"{style['primary_color']},{style['secondary_color']},"
        f"{style['outline_color']},{style['back_color']},"
        f"{1 if style['bold'] else 0},{1 if style['italic'] else 0},0,0,100,100,0,0,1,"
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
        resolved_styles[resolved["style_name"]] = resolved

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
            safe_text = _escape_ass_text(plain)

        if resolved["pos"] is not None:
            pos_x, pos_y = resolved["pos"]
            safe_text = rf"{{\pos({pos_x},{pos_y})}}{safe_text}"
        events.append(
            f"Dialogue: 0,{_ass_time(float(cue['start']))},{_ass_time(float(cue['end']))},"
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
