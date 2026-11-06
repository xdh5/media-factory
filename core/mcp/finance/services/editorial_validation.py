"""校验财经定稿的正文、钩子和封面。"""

from __future__ import annotations

from ..config.settings import ARTICLE_MAX_CHARACTERS, ARTICLE_MAX_LINE_LENGTH, ARTICLE_MIN_CHARACTERS, SOURCE_MAX_CHARACTERS, SOURCE_MIN_CHARACTERS
from ..errors import WorkflowStepError
from .narration import bare_text
from .save_draft import _cover_highlights, _cover_lines

BRAND_NAME = "财富研习岛"


def _brand_replacements(value) -> list[tuple[str, str]]:
    rows = []
    for item in value if isinstance(value, list) else []:
        if not isinstance(item, dict):
            continue
        source = str(item.get("from") or "").strip()
        target = str(item.get("to") or "").strip() or BRAND_NAME
        if source and target and source != target:
            rows.append((source, target))
    return rows


def _replace(text: str, rows: list[tuple[str, str]]) -> str:
    result = str(text or "")
    for source, target in rows:
        result = result.replace(source, target)
    return result


def validate_source_hook(source_text: str, hook: str) -> None:
    source = str(source_text or "").strip()
    if not hook or not source.startswith(hook):
        raise WorkflowStepError("source_hook 必须从数据库原稿第一个字开始连续复制，且与原稿开头完全一致")


def validate_article(source_text: str, source_hook: str, editorial: dict) -> dict:
    replacements = _brand_replacements(editorial.get("replacements"))
    mismatched = [row for row in replacements if bare_text(row[1]) != bare_text(BRAND_NAME)]
    if mismatched:
        raise WorkflowStepError(f"所有品牌只能替换为「{BRAND_NAME}」")
    processed_hook = _replace(source_hook, replacements)
    article = str(editorial.get("article") or "").strip()
    if not bare_text(article).startswith(bare_text(processed_hook)):
        raise WorkflowStepError("正文必须以完成品牌替换后的黄金钩子原样开头")
    long_lines = [(index, len(line.strip())) for index, line in enumerate(article.splitlines(), 1) if len(line.strip()) > ARTICLE_MAX_LINE_LENGTH]
    if long_lines:
        detail = "、".join(f"第{index}行 {size}字" for index, size in long_lines)
        raise WorkflowStepError(f"正文存在超过 {ARTICLE_MAX_LINE_LENGTH} 字的行：{detail}", {"long_lines": long_lines})
    source_size = len(bare_text(source_text))
    if not SOURCE_MIN_CHARACTERS <= source_size <= SOURCE_MAX_CHARACTERS:
        raise WorkflowStepError(f"校对稿有 {source_size} 字，超出 {SOURCE_MIN_CHARACTERS}～{SOURCE_MAX_CHARACTERS} 字，采集时须换稿")
    article_size = len(bare_text(article))
    if not ARTICLE_MIN_CHARACTERS <= article_size <= ARTICLE_MAX_CHARACTERS:
        raise WorkflowStepError(f"定稿有 {article_size} 字，须控制在 {ARTICLE_MIN_CHARACTERS}～{ARTICLE_MAX_CHARACTERS} 字")
    if article_size > len(bare_text(_replace(source_text, replacements))):
        raise WorkflowStepError("定稿只能压缩细节，不得扩写补足字数")
    return {"article": article, "source_hook": processed_hook, "replacements": editorial.get("replacements") or []}


def validate_cover(title: str, editorial: dict) -> dict:
    lines = _cover_lines(editorial.get("cover_lines"))
    if bare_text("".join(lines)) != bare_text(title):
        raise WorkflowStepError("封面各行拼接后的文字必须与确定标题一致")
    highlights = _cover_highlights(title, editorial.get("cover_highlights"))
    return {"cover_lines": lines, "cover_highlights": highlights}
