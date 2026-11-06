"""宿主编辑财经定稿，统一校验后写入稿件库。"""

from core.tools.media_records.client import _request
from ..errors import WorkflowStepError
from .editorial_validation import validate_article, validate_cover, validate_source_hook
from .metadata_validation import validate_metadata
from .save_draft import _SERIAL_REFERENCE_PATTERN


def validate_editorial(source_text: str, editorial: dict) -> dict:
    """检查正文、黄金钩子、标题标签及封面定稿。"""
    if not isinstance(editorial, dict):
        raise WorkflowStepError("正常稿件必须提供 editorial 定稿对象")
    original_hook = str(editorial.get("db_source_hook") or "").strip()
    validate_source_hook(source_text, original_hook)
    article = validate_article(source_text, original_hook, editorial)
    if article["source_hook"] != editorial.get("source_hook"):
        raise WorkflowStepError("source_hook 必须对应原稿钩子的品牌替换结果")
    if _SERIAL_REFERENCE_PATTERN.search(article["article"]):
        raise WorkflowStepError("定稿正文不能包含连载指涉")
    metadata = validate_metadata(
        editorial.get("title") or "", editorial.get("short_title") or "", editorial.get("hashtags") or [],
    )
    visual = validate_cover(metadata["title"], editorial)
    topic = str(editorial.get("topic") or "").strip()
    if not topic:
        raise WorkflowStepError("定稿 topic 不能为空")
    return {**editorial, **article, **metadata, **visual, "topic": topic, "db_source_hook": original_hook}


def list_editorial_drafts(missing_only: bool = True) -> dict:
    """只读返回未使用稿件及其定稿，不占用稿件。"""
    return _request("GET", "/v1/finance-editorial-drafts", query={"missing_only": str(missing_only).lower()})


def save_editorial_drafts(records: list[dict]) -> dict:
    """保存宿主 Agent 编写的未使用稿件定稿。"""
    sources = {row["aweme_id"]: row for row in list_editorial_drafts(False)["records"]}
    validated = []
    for record in records:
        source = sources.get(str(record["aweme_id"]))
        if source is None:
            raise WorkflowStepError("只能定稿未使用的财经稿件")
        validated.append({"aweme_id": record["aweme_id"], "editorial": validate_editorial(source["transcript_corrected"], record["editorial"])})
    return _request("POST", "/v1/finance-editorial-drafts", body={"records": validated})
