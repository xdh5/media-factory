"""本地章节标题截取。"""

import re
from ._constants import FALLBACK_TITLE_PREFIX
from ._errors import InvalidParameterError

_PUNCTUATION_PATTERN = re.compile(r"[，。！？；：、,.!?;:…\s]")


def _fallback_title(index: int, text: str) -> str:
    cleaned = _PUNCTUATION_PATTERN.sub("", str(text or "")).strip()
    if len(cleaned) >= 2:
        return cleaned[:4]
    return f"{FALLBACK_TITLE_PREFIX}{index + 1}"


def fallback_chapter_titles(chapter_texts: list[str]) -> list[str]:
    """本地标题：取本章开头文字截断。"""
    if not chapter_texts:
        raise InvalidParameterError("chapter_texts", "至少需要一个章节的正文片段")
    return [_fallback_title(index, text) for index, text in enumerate(chapter_texts)]
