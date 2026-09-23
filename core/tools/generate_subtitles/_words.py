"""逐词字幕：词级时间获取、分词、按预设动画生成 ASS 事件。

词级时间两种来源：
1. cue 显式提供 ``words``（推荐，时间可为整片绝对时间或相对 cue 起点，
   自动识别：全部词时长不超过 cue 时长且 cue 起点大于 0 时按相对处理）。
2. 未提供时按文本自动均匀切分：中文逐字、英文按空格分词，
   时间按词宽在 cue 区间内等比分布（口播节奏稳定时效果足够）。

显示分组为 块-行-词 三层：一个块最多 max_lines 行同屏显示，
块内逐词出事件，当前词带动画标签；超出一块后开新块（时间上顺延）。

动画标签与 ai-video-captions 的 subtitles.py 对齐：
highlight=换色、karaoke=\\kf 颜色扫过、scale=放大 110%、bounce=弹跳后回落。
"""

from __future__ import annotations

import re

from ._errors import InvalidParameterError
from ._text import _escape_ass_text, _line_width


def build_word_units(cue: dict, *, parameter: str) -> list[dict]:
    """把 cue 的词级时间规整为绝对时间单位列表。"""
    cue_start = float(cue["start"])
    cue_end = float(cue["end"])
    cue_duration = cue_end - cue_start
    if cue_duration <= 0:
        raise InvalidParameterError(f"{parameter}.end", f"cue 时长必须大于 0，当前 {cue_duration:.3f}s")

    words = cue.get("words")
    if words is not None:
        return _units_from_words(words, cue_start, cue_duration, parameter)
    return _units_from_text(str(cue["text"]), cue_start, cue_duration)


def _validate_unit(item: object, index: int, parameter: str) -> tuple[str, float, float]:
    item_parameter = f"{parameter}[{index}]"
    if not isinstance(item, dict):
        raise InvalidParameterError(item_parameter, "每个词必须是对象")
    text = str(item.get("text") or "").strip()
    if not text:
        raise InvalidParameterError(f"{item_parameter}.text", "词文本不能为空")
    try:
        start = float(item["start"])
        end = float(item["end"])
    except (KeyError, TypeError, ValueError) as error:
        raise InvalidParameterError(item_parameter, "每个词必须包含数值 start 与 end") from error
    if start < 0 or end <= start:
        raise InvalidParameterError(
            item_parameter, f"词时间必须满足 0 <= start < end，收到 {start} ~ {end}",
        )
    return text, start, end


def _units_from_words(
    words: list, cue_start: float, cue_duration: float, parameter: str,
) -> list[dict]:
    if not isinstance(words, list) or not words:
        raise InvalidParameterError(parameter, "words 必须是至少一个词的对象数组")
    units = [_validate_unit(item, index, parameter) for index, item in enumerate(words)]
    max_end = max(end for _, _, end in units)
    if max_end <= cue_duration + 0.05 and cue_start > 0:
        units = [(text, cue_start + start, cue_start + end) for text, start, end in units]
    for index, (text, start, end) in enumerate(units):
        if start < cue_start - 0.05 or end > cue_start + cue_duration + 0.05:
            raise InvalidParameterError(
                f"{parameter}[{index}]",
                f"词时间 {start:.3f}~{end:.3f} 超出 cue 范围 {cue_start:.3f}~{cue_start + cue_duration:.3f}；"
                "words 时间应为整片绝对时间或相对 cue 起点",
            )
    return [{"text": text, "start": start, "end": end} for text, start, end in units]


_CJK_SPLIT_PATTERN = re.compile(r"[A-Za-z0-9]+(?:['’.-][A-Za-z0-9]+)*|.")


def _units_from_text(text: str, cue_start: float, cue_duration: float) -> list[dict]:
    tokens = [token for token in _CJK_SPLIT_PATTERN.findall(text) if token.strip()]
    if not tokens:
        raise InvalidParameterError("text", "cue 文本没有可切分的词")
    widths = [max(1, _line_width(token)) for token in tokens]
    total_width = sum(widths)
    scale = cue_duration / total_width
    cursor = cue_start
    units: list[dict] = []
    for token, width in zip(tokens, widths):
        span = width * scale
        units.append({"text": token, "start": cursor, "end": cursor + span})
        cursor += span
    # 修正浮点累计误差，把最后一个词对齐到 cue 结束
    units[-1]["end"] = cue_start + cue_duration
    return units


def _split_display_lines(
    units: list[dict], *, max_width: int,
) -> list[list[dict]]:
    """按逻辑宽度切显示行；单行超宽时由 libass 兜底换行（WrapStyle: 0）。"""
    lines: list[list[dict]] = []
    current: list[dict] = []
    width = 0
    for unit in units:
        unit_width = _line_width(unit["text"])
        if current and width + unit_width > max_width:
            lines.append(current)
            current = [unit]
            width = unit_width
        else:
            current.append(unit)
            width += unit_width
    if current:
        lines.append(current)
    return lines


def _group_into_blocks(
    units: list[dict], *, max_width: int, max_lines: int,
) -> list[list[list[dict]]]:
    """块-行-词：一个块最多 max_lines 行同屏；行数超出时新开一块。"""
    display_lines = _split_display_lines(units, max_width=max_width)
    blocks: list[list[list[dict]]] = []
    for start in range(0, len(display_lines), max_lines):
        blocks.append(display_lines[start:start + max_lines])
    return blocks


def _uppercase(text: str) -> str:
    return text.upper()


def _is_latinish(text: str) -> bool:
    return any(char.isascii() and char.isalnum() for char in text)


def _animation_tag(animation: str, unit: dict, highlight_color: str) -> str:
    # karaoke 的 \kf 时长用词的真实时长，保证填色在本词窗口内走完；
    # 其他动画沿用最短 30cs 的保守时长。
    duration_cs = max(30, int((unit["end"] - unit["start"]) * 100))
    if animation == "karaoke":
        duration_cs = max(1, int(round((unit["end"] - unit["start"]) * 100)))
        return rf"{{\kf{duration_cs}\c{highlight_color}&}}"
    if animation == "scale":
        return rf"{{\fscx110\fscy110\c{highlight_color}&}}"
    if animation == "bounce":
        return (
            r"{\t(0,50,\fscx120\fscy120)"
            r"\t(50,100,\fscx100\fscy100)"
            rf"\c{highlight_color}&}}"
        )
    return rf"{{\c{highlight_color}&}}"


def build_word_events(
    units: list[dict],
    resolved: dict,
    language: str,
) -> list[tuple[float, float, str]]:
    """生成逐词 ASS 事件（start, end, text）；每条事件展示整块文本，当前词带动画。"""
    animation = resolved["animation"]
    highlight_color = resolved["highlight_color"]
    if not highlight_color:
        raise InvalidParameterError(
            "style", "逐词动画需要设置 highlight_color（或使用内置 preset）",
        )

    blocks = _group_into_blocks(
        units, max_width=resolved["max_width"], max_lines=resolved["max_lines"],
    )
    uppercase = resolved.get("uppercase", False)
    letter_spacing = resolved.get("letter_spacing")

    events: list[tuple[float, float, str]] = []
    for block in blocks:
        block_lines = [
            [_uppercase(unit["text"]) if uppercase else unit["text"] for unit in line]
            for line in block
        ]
        for line_index, line in enumerate(block):
            for word_index, unit in enumerate(line):
                if word_index + 1 < len(line):
                    event_end = line[word_index + 1]["start"]
                else:
                    event_end = unit["end"]

                parts: list[str] = []
                for row, (candidate_line, candidate_texts) in enumerate(zip(block, block_lines)):
                    if row > 0:
                        parts.append(r"\N")
                    # karaoke：当前词之前的词（含前面几行）保持高亮色，实现从左到右累积扫色
                    sung_row = row < line_index
                    for position, (candidate, text) in enumerate(zip(candidate_line, candidate_texts)):
                        escaped = _escape_ass_text(text)
                        if row == line_index and position == word_index:
                            parts.append(_animation_tag(animation, candidate, highlight_color))
                            parts.append(escaped)
                            parts.append(r"{\r}")
                        elif animation == "karaoke" and (sung_row or position < word_index):
                            parts.append(rf"{{\c{highlight_color}&}}{escaped}{{\r}}")
                        else:
                            parts.append(escaped)
                        if position + 1 < len(candidate_line):
                            neighbor = candidate_line[position + 1]
                            neighbor_text = candidate_texts[position + 1]
                            if _is_latinish(text) or _is_latinish(neighbor_text):
                                parts.append(" ")
                body = "".join(parts)
                if letter_spacing:
                    body = rf"{{\fsp{letter_spacing}}}{body}"
                events.append((unit["start"], event_end, body))

    return events
