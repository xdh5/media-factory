"""校验共用发布文案并生成分段标题。"""

from __future__ import annotations

from .._errors import AnimeError


def part_title(title: str, index: int, count: int) -> str:
    """多段成片在标题末尾标明当前集数，单段保持原题。"""
    text = str(title).strip()
    if count <= 1:
        return text[:100]
    suffix = f"｜第{index}集（共{count}集）"
    return f"{text[:100 - len(suffix)].rstrip()}{suffix}"


def validate_copy(titles: list[str], descriptions: list[str], tags: list[str],
                  *, require_completed: bool = True) -> None:
    """执行包只接受一份共用发布文案。"""
    max_title_length = 80 if require_completed else 100
    if len(titles) != 1 or not titles[0].strip() or len(titles[0]) > max_title_length:
        raise AnimeError(f"请提供一个 1 到 {max_title_length} 字符的共用标题")
    if len(descriptions) != 1 or not descriptions[0].strip() or len(descriptions[0]) > 5000:
        raise AnimeError("请提供一个 1 到 5000 字符的共用描述")
    if not all(isinstance(tag, str) and tag.strip() and not tag.startswith("#") for tag in tags):
        raise AnimeError("标签必须为不带 # 的非空文字")
    if len(set(tags)) != len(tags) or sum(len(tag) + 3 for tag in tags) > 420:
        raise AnimeError("标签须去重，总预算不得超过 420 字符")
    if require_completed and "已完结" not in titles[0]:
        raise AnimeError("YouTube 标题关键词必须包含“已完结”")
    if require_completed and "#已完结" not in descriptions[0]:
        raise AnimeError("YouTube 描述底部 hashtag 必须包含 #已完结")
    if require_completed and "已完结" not in {tag.strip().lstrip("#") for tag in tags}:
        raise AnimeError("YouTube 搜索标签必须包含“已完结”")
