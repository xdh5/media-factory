"""标题标签格式校验。"""

from __future__ import annotations

from ..errors import AgentOutputFormatError


def validate_metadata(title: str, short_title: str, hashtags: list[str]) -> dict:
    """归一化长短标题和四个标签，校验各字段的格式。"""
    if not isinstance(hashtags, list) or len(hashtags) != 4:
        raise AgentOutputFormatError("hashtags 必须包含四个标签")
    fields = [str(field).strip().lstrip("#") for field in (title, short_title, *hashtags)]
    if any(not field or "|" in field or len(field.splitlines()) != 1 for field in fields):
        raise AgentOutputFormatError("长标题、短标题和标签必须为不含竖线的单行文字")
    # 在字数校验前去掉模型偶尔生成的尾部句末标点，避免标题标点单独占行。
    fields[0] = fields[0].rstrip("。．.？?！!… \t")
    fields[1] = fields[1].rstrip("。．.？?！!… \t")
    if not 12 <= len(fields[0]) <= 26:
        raise AgentOutputFormatError("中文长标题必须为 12～26 个字符")
    if not 6 <= len(fields[1]) <= 16:
        raise AgentOutputFormatError("中文短标题必须为 6～16 个字符")
    if len(set(fields[2:])) != 4:
        raise AgentOutputFormatError("四个标签必须互不重复")
    return {"title": fields[0], "short_title": fields[1], "hashtags": fields[2:]}
