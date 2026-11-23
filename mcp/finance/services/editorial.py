"""财经原稿内容校验与宿主定稿保存。"""

from xml.etree import ElementTree

from workflows.finance.parameters import ARTICLE_MAX_LINE_LENGTH
from workflows.finance.errors.exceptions import WorkflowStepError
from workflows.finance.tools.drafts import bare_text, validate_metadata, _cover_lines, _cover_highlights, _SERIAL_REFERENCE_PATTERN
from workflows.finance.infrastructure.scripts import list_editorial_drafts
from media_factory_mcp.finance.infrastructure.collection import write_editorial_drafts

BRAND_NAME = "大鹅"


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


def validate_source_hook(source_text: str, hook: str) -> None:
    source = str(source_text or "").strip()
    if not hook or hook not in source:
        raise WorkflowStepError("db_source_hook 必须是数据库原稿中的连续原文片段")


def validate_article(editorial: dict) -> dict:
    replacements = _brand_replacements(editorial.get("replacements"))
    mismatched = [row for row in replacements if bare_text(row[1]) != bare_text(BRAND_NAME)]
    if mismatched:
        raise WorkflowStepError(f"所有品牌只能替换为「{BRAND_NAME}」")
    processed_hook = str(editorial["source_hook"]).strip()
    article = str(editorial.get("article") or "").strip()
    if not bare_text(article).startswith(bare_text(processed_hook)):
        raise WorkflowStepError("正文必须以定稿黄金钩子开头")
    long_lines = [(index, len(line.strip())) for index, line in enumerate(article.splitlines(), 1) if len(line.strip()) > ARTICLE_MAX_LINE_LENGTH]
    if long_lines:
        detail = "、".join(f"第{index}行 {size}字" for index, size in long_lines)
        raise WorkflowStepError(f"正文存在超过 {ARTICLE_MAX_LINE_LENGTH} 字的行：{detail}", {"long_lines": long_lines})
    return {"article": article, "source_hook": processed_hook, "replacements": editorial.get("replacements") or []}


def validate_cover(title: str, editorial: dict) -> dict:
    lines = _cover_lines(editorial.get("cover_lines"))
    if bare_text("".join(lines)) != bare_text(title):
        raise WorkflowStepError("封面各行拼接后的文字必须与确定标题一致")
    highlights = _cover_highlights(title, editorial.get("cover_highlights"))
    return {"cover_lines": lines, "cover_highlights": highlights}


def validate_editorial(source_text: str, editorial: dict) -> dict:
    """检查正文、黄金钩子、标题标签及封面定稿。"""
    if not isinstance(editorial, dict):
        raise WorkflowStepError("正常稿件必须提供 editorial 定稿对象")
    original_hook = str(editorial.get("db_source_hook") or "").strip()
    validate_source_hook(source_text, original_hook)
    article = validate_article(editorial)
    if _SERIAL_REFERENCE_PATTERN.search(article["article"]):
        raise WorkflowStepError("定稿正文不能包含连载指涉")
    metadata = validate_metadata(
        editorial.get("title") or "", editorial.get("short_title") or "", editorial.get("hashtags") or [],
    )
    visual = validate_cover(metadata["title"], editorial)
    storyboard = str(editorial.get("storyboard") or "").strip()
    shots = [row for row in storyboard.splitlines() if row.strip()]
    narration = [row for row in article["article"].splitlines() if row.strip()]
    if editorial.get('ssml') is not None:
        markup = editorial['ssml']
        if not isinstance(markup, list) or len(markup) != len(narration):
            raise WorkflowStepError('SSML 须与正文逐行对应')
        for text, value in zip(narration, markup, strict=True):
            root = ElementTree.fromstring(value)
            if ''.join(''.join(root.itertext()).split()) != ''.join(text.split()):
                raise WorkflowStepError('SSML 文字须与对应正文一致')
            if any(set(element.attrib) & {'pitch', 'contour', 'range'} for element in root.iter()):
                raise WorkflowStepError('配音不能调整音高')
    if editorial.get("storyboard_status") != "pending" and (len(shots) != len(narration) or any(len(row.split("|")) != 2 for row in shots)):
        raise WorkflowStepError("storyboard 须与正文逐行对应，格式为：画面描述|搜索关键词")
    topic = str(editorial.get("topic") or "").strip()
    if not topic:
        raise WorkflowStepError("定稿 topic 不能为空")
    return {**editorial, **article, **metadata, **visual, "topic": topic, "storyboard": storyboard, "db_source_hook": original_hook}


def save_editorial_drafts(records: list[dict]) -> dict:
    """保存宿主 Agent 编写的未使用稿件定稿。"""
    sources = {row["aweme_id"]: row for row in list_editorial_drafts(False)["records"]}
    validated = []
    for record in records:
        source = sources.get(str(record["aweme_id"]))
        if source is None:
            raise WorkflowStepError("只能定稿未使用的财经稿件")
        validated.append({"aweme_id": record["aweme_id"], "editorial": validate_editorial(source["transcript_corrected"], record["editorial"])})
    return write_editorial_drafts(validated)
