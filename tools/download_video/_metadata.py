"""从平台文案收集话题，保持出现顺序。"""

from __future__ import annotations

import re

_HASHTAG_RE = re.compile(r"#([^\s#]+)")


def collect_topics(description: str = "", tags: list | None = None) -> list[str]:
    """先取描述里的 #话题，再补上平台标签里尚未出现的项。"""
    topics: list[str] = []
    seen: set[str] = set()

    def add(raw: str) -> None:
        text = str(raw or "").strip().lstrip("#").strip()
        if not text:
            return
        tag = f"#{text}"
        if tag in seen:
            return
        seen.add(tag)
        topics.append(tag)

    for name in _HASHTAG_RE.findall(description or ""):
        add(name)
    for tag in tags or []:
        add(str(tag))
    return topics
