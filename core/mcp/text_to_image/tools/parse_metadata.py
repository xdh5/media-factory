"""标题标签格式校验。"""

from __future__ import annotations

from .._errors import AgentOutputFormatError


def parse_metadata(value: str) -> dict:
    line = next((line.strip() for line in value.splitlines() if "|" in line), "")
    fields = [field.strip().lstrip("#") for field in line.split("|")]
    if len(fields) != 6 or any(not field for field in fields):
        raise AgentOutputFormatError("标题标签必须严格输出：长标题|短标题|标签一|标签二|标签三|标签四")
    if not 12 <= len(fields[0]) <= 26:
        raise AgentOutputFormatError("中文长标题必须为 12～26 个字符")
    if not 6 <= len(fields[1]) <= 16:
        raise AgentOutputFormatError("中文短标题必须为 6～16 个字符")
    if len(set(fields[2:])) != 4:
        raise AgentOutputFormatError("四个标签必须互不重复")
    return {"title": fields[0], "short_title": fields[1], "hashtags": fields[2:]}
