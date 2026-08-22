"""财经旁白切句与字幕显示：TTS 按标点切段，屏上默认去标点、顿号保留。"""

from __future__ import annotations

import re

SUBTITLE_MAX_CONTENT_CHARS = 20
# 屏上重点样式（与财经 Skill 一致）：相对默认 100 的 130%，金色
SUBTITLE_EMPHASIS_STYLE = {"font_size": 130, "primary_color": "#FFD54A"}
_CONTENT_CHAR = re.compile(r"[\u4e00-\u9fffA-Za-z0-9]")
_ENUMERATION = re.compile(
    r"[\u4e00-\u9fffA-Za-z0-9]{1,8}(?:、[\u4e00-\u9fffA-Za-z0-9]{1,8})+"
)
_STRONG_BREAK = set("。！？；!?")
_COMMA_BREAK = set("，,")
_STRIP_FOR_DISPLAY = "。，；！？,.!?;:：…—～~\"'“”‘’（）()《》[] "


def content_char_count(text: str) -> int:
    return len(_CONTENT_CHAR.findall(text or ""))


def display_subtitle_text(text: str) -> str:
    """屏上默认去掉句读标点；顿号「、」留下。标记括号【】不进入画面。"""
    raw = str(text or "").strip().replace("【", "").replace("】", "")
    if not raw:
        return ""
    chars: list[str] = []
    for char in raw:
        if char == "、":
            chars.append("、")
            continue
        if char in _STRIP_FOR_DISPLAY or char.isspace():
            continue
        chars.append(char)
    return "".join(chars).strip()


def parse_emphasis_segments(text: str) -> list[tuple[str, bool]]:
    """按【】切成 (原文片段, 是否重点)。括号本身不进入片段。"""
    raw = str(text or "")
    segments: list[tuple[str, bool]] = []
    index = 0
    while index < len(raw):
        char = raw[index]
        if char == "【":
            close = raw.find("】", index + 1)
            if close < 0:
                raise ValueError("重点标记【没有对应的】")
            inner = raw[index + 1:close]
            if "【" in inner or "】" in inner:
                raise ValueError("重点标记【】不能嵌套")
            if not inner.strip():
                raise ValueError("【】内不能为空")
            segments.append((inner, True))
            index = close + 1
            continue
        if char == "】":
            raise ValueError("重点标记】没有对应的【")
        next_mark = raw.find("【", index)
        if next_mark < 0:
            next_mark = len(raw)
        close = raw.find("】", index)
        if 0 <= close < next_mark:
            raise ValueError("重点标记】没有对应的【")
        segments.append((raw[index:next_mark], False))
        index = next_mark
    return segments


def display_subtitle_cue(text: str) -> str | list[dict]:
    """去标点后的屏上文本；有【】时返回带重点样式的分段。"""
    rendered: list[tuple[str, bool]] = []
    for chunk, emphasized in parse_emphasis_segments(str(text or "").strip()):
        shown = display_subtitle_text(chunk)
        if shown:
            rendered.append((shown, emphasized))
    if not rendered:
        return ""
    if not any(emphasized for _, emphasized in rendered):
        return "".join(chunk for chunk, _ in rendered)
    spans: list[dict] = []
    for chunk, emphasized in rendered:
        span: dict = {"text": chunk}
        if emphasized:
            span["style"] = dict(SUBTITLE_EMPHASIS_STYLE)
        spans.append(span)
    return spans


def _enumeration_ranges(text: str) -> list[tuple[int, int]]:
    return [match.span() for match in _ENUMERATION.finditer(text)]


def _inside_enumeration(index: int, ranges: list[tuple[int, int]]) -> bool:
    return any(start < index < end for start, end in ranges)


def _split_by_breaks(text: str) -> list[str]:
    pieces: list[str] = []
    buf: list[str] = []
    ranges = _enumeration_ranges(text)
    for index, char in enumerate(text):
        buf.append(char)
        if _inside_enumeration(index, ranges):
            continue
        if char in _STRONG_BREAK or char in _COMMA_BREAK:
            piece = "".join(buf).strip()
            if piece:
                pieces.append(piece)
            buf = []
    tail = "".join(buf).strip()
    if tail:
        pieces.append(tail)
    return pieces or ([text.strip()] if text.strip() else [])


def _best_semantic_cut(text: str) -> int | None:
    length = len(text)
    if length < 4:
        return None
    ranges = _enumeration_ranges(text)
    lo = max(1, length // 3)
    hi = min(length - 1, (length * 2) // 3)
    mid = length // 2
    candidates = list(range(mid, hi + 1)) + list(range(mid - 1, lo - 1, -1))
    for index in candidates:
        if _inside_enumeration(index, ranges):
            continue
        if text[index - 1] in _STRONG_BREAK | _COMMA_BREAK | set("、"):
            continue
        return index
    for index in candidates:
        if not _inside_enumeration(index, ranges):
            return index
    return None


def _split_long(text: str) -> list[str]:
    if content_char_count(text) <= SUBTITLE_MAX_CONTENT_CHARS:
        return [text]
    cut = _best_semantic_cut(text)
    if cut is None:
        return [text]
    left, right = text[:cut].strip(), text[cut:].strip()
    if not left or not right:
        return [text]
    return _split_long(left) + _split_long(right)


def split_narration_lines(article: str) -> list[str]:
    """把正文切成 TTS 一句一条：先按行，再按标点，超长再拆。"""
    lines: list[str] = []
    for raw in str(article or "").splitlines():
        block = raw.strip()
        if not block:
            continue
        for piece in _split_by_breaks(block):
            lines.extend(_split_long(piece))
    return lines
