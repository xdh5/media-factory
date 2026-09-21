"""心灵鸡汤文章稿件校验与保存。"""

from __future__ import annotations

import json
from pathlib import Path

from .._constants import ARTICLE_MAX_LENGTH, DRAFT_FILE_NAME, MCP_ID, production_dirs, production_run_id
from .._errors import WorkflowStepError
from .parse_metadata import parse_metadata

ARTICLE_MIN_LENGTH = 300
CONTENT_KIND = "article"


def load_draft(path: str | Path, label: str) -> tuple[Path, dict]:
    resolved = Path(path).resolve()
    if not resolved.is_file():
        raise WorkflowStepError(f"{label}不存在：{resolved}")
    try:
        payload = json.loads(resolved.read_text(encoding="utf-8"))
    except (OSError, json.JSONDecodeError) as exc:
        raise WorkflowStepError(f"读取{label}失败：{resolved}。{exc}") from exc
    if not isinstance(payload, dict):
        raise WorkflowStepError(f"{label}必须是 JSON 对象：{resolved}")
    return resolved, payload


def _cover_lines(values: list[str]) -> list[str]:
    if not isinstance(values, list) or not 1 <= len(values) <= 3:
        raise WorkflowStepError("cover_lines 必须包含1～3行")
    lines = [str(item or "").strip() for item in values]
    if any(not item for item in lines):
        raise WorkflowStepError("cover_lines 不能包含空行")
    return lines


def _cover_highlights(title: str, values: list[str]) -> list[str]:
    if not isinstance(values, list) or not 1 <= len(values) <= 3:
        raise WorkflowStepError("cover_highlights 必须包含1～3项")
    highlights = [str(item or "").strip() for item in values]
    if any(not item or item not in title for item in highlights):
        raise WorkflowStepError("cover_highlights 的每个重点词都必须原样出现在 title 中")
    return highlights


def validate_article_fields(
    *, article: str, intro_scene: str, title: str, short_title: str,
    hashtags: list[str], cover_lines: list[str], cover_highlights: list[str],
) -> dict:
    normalized_article = str(article or "").strip()
    article_length = len("".join(normalized_article.split()))
    if article_length < ARTICLE_MIN_LENGTH:
        raise WorkflowStepError(
            f"心灵鸡汤正文去除空白后不得少于 {ARTICLE_MIN_LENGTH} 个字符，当前为 {article_length} 个字符"
        )
    if article_length > ARTICLE_MAX_LENGTH:
        raise WorkflowStepError(
            f"心灵鸡汤正文去除空白后不得超过 {ARTICLE_MAX_LENGTH} 个字符，当前为 {article_length} 个字符。"
            "请按成稿规则压缩到 1000 字左右：保留原文结构、黄金钩子和原话，只删改细枝末节"
        )
    long_lines = [
        (index, len(line.strip()))
        for index, line in enumerate(normalized_article.splitlines(), 1)
        if len(line.strip()) > 20
    ]
    if long_lines:
        raise WorkflowStepError("心灵鸡汤正文每行不得超过20字", {"long_lines": long_lines})
    normalized_intro_scene = str(intro_scene or "").strip()
    if not normalized_intro_scene:
        raise WorkflowStepError(
            "intro_scene 不能为空：请从文章提炼一句片头写实图场景描述"
            "（人物身份 + 关键动作 + 环境细节）"
        )
    metadata = parse_metadata("|".join([str(title), str(short_title), *(str(item) for item in hashtags)]))
    return {
        "article": normalized_article,
        "intro_scene": normalized_intro_scene,
        "metadata": metadata,
        "cover_lines": _cover_lines(cover_lines),
        "cover_highlights": _cover_highlights(metadata["title"], cover_highlights),
    }


def save_article_draft(
    *, topic: str, article: str, intro_scene: str, title: str, short_title: str,
    hashtags: list[str], cover_lines: list[str], cover_highlights: list[str],
    publish_date: str, topic_record: dict, draft_path: str | Path | None = None,
) -> dict:
    normalized_topic = str(topic or "").strip()
    if not normalized_topic:
        raise WorkflowStepError("topic 不能为空")
    validated = validate_article_fields(
        article=article, intro_scene=intro_scene, title=title, short_title=short_title,
        hashtags=hashtags, cover_lines=cover_lines, cover_highlights=cover_highlights,
    )
    if draft_path is None:
        run_id = production_run_id(publish_date)
        cache_root, output_root = production_dirs(run_id)
        target = cache_root / DRAFT_FILE_NAME
        record_id = int(topic_record["id"])
    else:
        resolved, existing = load_draft(draft_path, "待修改心灵鸡汤稿件")
        if normalized_topic != str(existing.get("topic") or "").strip():
            raise WorkflowStepError("修改已有心灵鸡汤稿件时不能更换话题")
        run_id = str(existing["run_id"])
        cache_root = Path(existing["cache_dir"]).resolve()
        output_root = Path(existing["output_dir"]).resolve()
        target = resolved
        record_id = int(existing["topic_record_id"])
    cache_root.mkdir(parents=True, exist_ok=True)
    output_root.mkdir(parents=True, exist_ok=True)
    draft = {
        "version": 2,
        "line": MCP_ID,
        "content_kind": CONTENT_KIND,
        "status": "ready_for_production",
        "topic": normalized_topic,
        "run_id": run_id,
        "topic_record_id": record_id,
        "database_status": "pending_publish",
        "publish_date": str(publish_date).strip(),
        "article": validated["article"],
        "intro_scene": validated["intro_scene"],
        **validated["metadata"],
        "cover_lines": validated["cover_lines"],
        "cover_highlights": validated["cover_highlights"],
        "cache_dir": str(cache_root),
        "output_dir": str(output_root),
        "draft_path": str(target),
    }
    target.write_text(json.dumps(draft, ensure_ascii=False, indent=2), encoding="utf-8")
    return draft
