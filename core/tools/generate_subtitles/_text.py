"""字幕文本解析与句内富文本 ASS 生成。"""

from __future__ import annotations

import re
import unicodedata

from ._errors import InvalidParameterError
from ._style import (
    INLINE_STYLE_KEYS,
    _style_fingerprint,
    _validate_options,
    build_inline_markup,
    resolve_subtitle_style,
)


def parse_cue_text(value: object, *, parameter: str = "text") -> list[dict]:
    """将 cue.text 解析为 span 列表；字符串视为单段纯文本。"""
    if isinstance(value, str):
        text = value.strip()
        if not text:
            return []
        return [{"text": text, "style": None}]
    if isinstance(value, list):
        spans: list[dict] = []
        for index, item in enumerate(value):
            span_parameter = f"{parameter}[{index}]"
            if not isinstance(item, dict):
                raise InvalidParameterError(span_parameter, "每个 text 分段必须是对象")
            text = str(item.get("text") or "")
            if not text:
                raise InvalidParameterError(f"{span_parameter}.text", "分段 text 不能为空")
            style = item.get("style")
            if style is not None:
                _validate_options(style, f"{span_parameter}.style", INLINE_STYLE_KEYS)
            spans.append({"text": text, "style": style})
        return spans
    raise InvalidParameterError(parameter, "text 必须是字符串或分段数组")


def validate_cue_text(value: object, *, parameter: str = "text") -> None:
    spans = parse_cue_text(value, parameter=parameter)
    if not spans:
        raise InvalidParameterError(parameter, "text 不能为空")


def _unit_width(value: str) -> int:
    return 2 if unicodedata.east_asian_width(value) in {"W", "F"} else 1


def wrap_plain_text(value: str, max_width: int, max_lines: int) -> str:
    """按逻辑宽度换行；合并到 max_lines 时仍遵守每行 max_width。"""
    cleaned = " ".join(str(value or "").replace("\r", " ").replace("\n", " ").split())
    lines = _wrap_lines(cleaned, max_width)
    if len(lines) <= max_lines:
        return r"\N".join(lines)
    return r"\N".join(_balance_lines(cleaned, max_width, max_lines))


def _line_width(value: str) -> int:
    return sum(_unit_width(char) for char in value)


def _wrap_lines(value: str, max_width: int) -> list[str]:
    tokens = re.findall(r"[A-Za-z0-9]+(?:['’.-][A-Za-z0-9]+)*|\s+|.", value)
    lines: list[str] = []
    current = ""
    width = 0
    for token in tokens:
        if token.isspace():
            if current and not current.endswith(" "):
                current += " "
                width += 1
            continue
        token_width = _line_width(token)
        if current and width + token_width > max_width:
            lines.append(current.rstrip())
            current = token
            width = token_width
        else:
            current += token
            width += token_width
    if current.strip():
        lines.append(current.rstrip())
    return lines or [""]


def _balance_lines(value: str, max_width: int, max_lines: int) -> list[str]:
    """把整句拆成不超过 max_lines 行，每行都不超过 max_width，尽量均衡。"""
    tokens = re.findall(r"[A-Za-z0-9]+(?:['’.-][A-Za-z0-9]+)*|\s+|.", value)
    token_widths = [_line_width(token) for token in tokens]
    total = sum(token_widths)
    if total <= max_width:
        return [value]

    best: list[list[int]] | None = None
    target = (total + max_lines - 1) // max_lines

    def search(start: int, row: int, widths: list[int], groups: list[list[int]]) -> None:
        nonlocal best
        if row == max_lines - 1:
            remaining = sum(token_widths[start:])
            if remaining <= max_width:
                candidate = groups + [list(range(start, len(tokens)))]
                if best is None or _balance_cost(candidate, token_widths, target) < _balance_cost(best, token_widths, target):
                    best = candidate
            return
        width = 0
        for end in range(start, len(tokens)):
            width += token_widths[end]
            if width > max_width:
                break
            remaining_rows = max_lines - row - 1
            remaining_width = sum(token_widths[end + 1:])
            if remaining_width > remaining_rows * max_width:
                continue
            search(end + 1, row + 1, widths + [width], groups + [list(range(start, end + 1))])
    search(0, 0, [], [])
    if best is None:
        return _wrap_lines(value, max_width)[:max_lines]
    return [_join_tokens(tokens, group) for group in best]


def _balance_cost(groups: list[list[int]], token_widths: list[int], target: int) -> int:
    return sum(abs(sum(token_widths[index] for index in group) - target) for group in groups)


def _join_tokens(tokens: list[str], indexes: list[int]) -> str:
    parts: list[str] = []
    for index in indexes:
        token = tokens[index]
        if token.isspace():
            if parts and not parts[-1].endswith(" "):
                parts.append(" ")
            continue
        parts.append(token)
    return "".join(parts).strip()


def _escape_ass_text(value: str) -> str:
    return value.replace("\\", r"\\").replace("{", "（").replace("}", "）")


def _merge_dict(base: dict | None, override: dict | None) -> dict | None:
    if base is None and override is None:
        return None
    merged: dict = dict(base or {})
    if override:
        merged.update(override)
    return merged


def _resolve_span_style(
    language: str,
    width: int,
    height: int,
    *,
    global_style: dict | None,
    cue_style: dict | None,
    span_style: dict | None,
    global_position: dict | None,
    cue_position: dict | None,
    parameter: str,
) -> dict:
    merged_style = _merge_dict(_merge_dict(global_style, cue_style), span_style)
    merged_position = _merge_dict(global_position, cue_position)
    return resolve_subtitle_style(
        language,
        width,
        height,
        style=merged_style,
        position=merged_position,
        style_parameter=f"{parameter}.style",
        position_parameter=f"{parameter}.position",
    )


def build_rich_ass_text(
    spans: list[dict],
    *,
    base_style: dict,
    language: str,
    width: int,
    height: int,
    global_style: dict | None = None,
    cue_style: dict | None = None,
    global_position: dict | None = None,
    cue_position: dict | None = None,
    parameter: str = "text",
) -> str:
    """把分段文本转成带 ASS 行内样式的字符串；换行交给 libass 按 MarginL/MarginR 处理。"""
    if not spans:
        return ""

    plain_parts: list[str] = []
    style_keys: list[str] = []
    resolved_by_key: dict[str, dict] = {"": base_style}

    for index, span in enumerate(spans):
        span_style = span.get("style")
        if span_style:
            resolved = _resolve_span_style(
                language,
                width,
                height,
                global_style=global_style,
                cue_style=cue_style,
                span_style=span_style,
                global_position=global_position,
                cue_position=cue_position,
                parameter=f"{parameter}[{index}]",
            )
            key = _style_fingerprint(resolved)
            resolved_by_key[key] = resolved
        else:
            key = ""
        plain_parts.append(str(span["text"]))
        style_keys.extend([key] * len(span["text"]))

    plain = "".join(plain_parts)
    wrapped = _wrap_rich_text(
        plain,
        style_keys,
        resolved_by_key,
        max_width=base_style["max_width"],
        max_lines=base_style["max_lines"],
    )
    return _inject_inline_styles(wrapped, plain, style_keys, resolved_by_key)


def _wrap_rich_text(
    plain: str,
    style_keys: list[str],
    resolved_by_key: dict[str, dict],
    *,
    max_width: int,
    max_lines: int,
) -> str:
    """按每个字的实际行内字号均衡换行，避免 libass 产生单字孤行。"""
    if not plain or max_lines <= 1:
        return plain

    base_style = resolved_by_key[""]
    base_font_size = max(1, int(base_style["font_size"]))
    widths = [
        _unit_width(char)
        * resolved_by_key[style_keys[index]]["font_size"]
        / base_font_size
        for index, char in enumerate(plain)
    ]
    if sum(widths) <= max_width:
        return plain

    break_candidates = [
        index
        for index in range(1, len(plain))
        if not plain[index].isspace() and not _inside_ascii_word(plain, index)
    ]
    for line_count in range(2, max_lines + 1):
        breaks = _best_rich_breaks(plain, widths, break_candidates, max_width, line_count)
        if breaks is not None:
            parts: list[str] = []
            start = 0
            for end in [*breaks, len(plain)]:
                # 必须保留原字符序列，供后续按原下标注入行内样式。
                parts.append(plain[start:end])
                start = end
            return r"\N".join(parts)
    return plain


def _inside_ascii_word(value: str, index: int) -> bool:
    """英文和数字单词内部不作为换行候选点。"""
    left = value[index - 1]
    right = value[index]
    return left.isascii() and right.isascii() and left.isalnum() and right.isalnum()


def _best_rich_breaks(
    plain: str,
    widths: list[float],
    candidates: list[int],
    max_width: int,
    line_count: int,
) -> list[int] | None:
    """寻找不超宽且各行尽量均衡的断点；单字行施加高惩罚。"""
    total_width = sum(widths)
    target_width = total_width / line_count
    best_breaks: list[int] | None = None
    best_cost: float | None = None

    def search(start: int, row: int, chosen: list[int], cost: float) -> None:
        nonlocal best_breaks, best_cost
        if row == line_count - 1:
            line_width = sum(widths[start:])
            if line_width > max_width:
                return
            final_cost = cost + _rich_line_cost(plain[start:], line_width, target_width)
            if best_cost is None or final_cost < best_cost:
                best_cost = final_cost
                best_breaks = list(chosen)
            return

        remaining_rows = line_count - row - 1
        for end in candidates:
            if end <= start or len(plain) - end < remaining_rows:
                continue
            line_width = sum(widths[start:end])
            if line_width > max_width:
                break
            next_cost = cost + _rich_line_cost(plain[start:end], line_width, target_width)
            if best_cost is not None and next_cost >= best_cost:
                continue
            search(end, row + 1, [*chosen, end], next_cost)

    search(0, 0, [], 0.0)
    return best_breaks


def _rich_line_cost(text: str, width: float, target_width: float) -> float:
    visible_chars = len(text.strip())
    orphan_penalty = target_width * target_width * 100 if visible_chars == 1 else 0
    return (width - target_width) ** 2 + orphan_penalty


def _inject_inline_styles(
    wrapped: str,
    plain: str,
    style_keys: list[str],
    resolved_by_key: dict[str, dict],
) -> str:
    base_style = resolved_by_key[""]
    plain_index = 0
    current_key = ""
    parts: list[str] = []
    index = 0
    while index < len(wrapped):
        if wrapped.startswith(r"\N", index):
            parts.append(r"\N")
            index += 2
            continue
        if plain_index >= len(plain):
            break
        next_key = style_keys[plain_index]
        if next_key != current_key:
            if current_key:
                parts.append(r"{\r}")
            if next_key:
                open_tag, _ = build_inline_markup(base_style, resolved_by_key[next_key])
                if open_tag:
                    parts.append(open_tag)
            current_key = next_key
        parts.append(_escape_ass_text(plain[plain_index]))
        plain_index += 1
        index += 1
    if current_key:
        parts.append(r"{\r}")
    return "".join(parts)
