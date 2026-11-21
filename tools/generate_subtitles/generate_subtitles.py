"""按时间轴写出 ASS 字幕文件。"""

from __future__ import annotations

from pathlib import Path

from ._ass import write_timeline_ass
from ._errors import InvalidParameterError
from ._fonts import resolve_fontsdir
from ._style import _POSITION_KEYS, _STYLE_KEYS, _validate_options
from ._text import validate_cue_text

__all__ = ["generate_subtitles"]


def _canvas_size(width: int, height: int) -> tuple[int, int]:
    try:
        canvas_width = int(width)
        canvas_height = int(height)
    except (TypeError, ValueError) as extra:
        raise InvalidParameterError("width/height", "画布宽高必须是整数") from extra
    if canvas_width < 2 or canvas_height < 2 or canvas_width % 2 or canvas_height % 2:
        raise InvalidParameterError(
            "width/height",
            f"画布宽高必须是大于等于 2 的偶数，当前为 {canvas_width}x{canvas_height}",
        )
    return canvas_width, canvas_height


def generate_subtitles(
    cues: list[dict],
    output_path: str | Path,
    width: int,
    height: int,
    *,
    style: dict | None = None,
    position: dict | None = None,
) -> dict:
    """按时间轴生成 ASS。cues 每项含 start、end、text，可选 language、style、position。"""
    if not isinstance(cues, list) or not cues:
        raise InvalidParameterError("cues", "cues 必须是至少一条字幕")
    global_style = _validate_options(style, "style", _STYLE_KEYS)
    global_position = _validate_options(position, "position", _POSITION_KEYS)
    for index, cue in enumerate(cues):
        if not isinstance(cue, dict):
            raise InvalidParameterError(f"cues[{index}]", "每条 cue 必须是对象")
        _validate_options(cue.get("style"), f"cues[{index}].style", _STYLE_KEYS)
        _validate_options(cue.get("position"), f"cues[{index}].position", _POSITION_KEYS)
        validate_cue_text(cue.get("text"), parameter=f"cues[{index}].text")
        words = cue.get("words")
        if words is not None:
            if not isinstance(words, list) or not words:
                raise InvalidParameterError(
                    f"cues[{index}].words", "words 必须是至少一个词的对象数组",
                )
            for word_index, item in enumerate(words):
                word_parameter = f"cues[{index}].words[{word_index}]"
                if not isinstance(item, dict) or not str(item.get("text") or "").strip():
                    raise InvalidParameterError(word_parameter, "每个词必须包含非空 text")
                for key in ("start", "end"):
                    value = item.get(key)
                    if isinstance(value, bool) or not isinstance(value, (int, float)):
                        raise InvalidParameterError(
                            f"{word_parameter}.{key}", "必须是数字（秒）",
                        )

    destination = Path(output_path).resolve()
    if destination.suffix.lower() != ".ass":
        raise InvalidParameterError("output_path", "输出必须使用 .ass 扩展名")
    destination.parent.mkdir(parents=True, exist_ok=True)
    canvas_width, canvas_height = _canvas_size(width, height)
    write_timeline_ass(
        destination,
        cues,
        canvas_width,
        canvas_height,
        style=global_style or None,
        position=global_position or None,
    )
    fontsdir = resolve_fontsdir()
    return {
        "output_path": str(destination),
        "fontsdir": str(fontsdir),
        "width": canvas_width,
        "height": canvas_height,
    }
