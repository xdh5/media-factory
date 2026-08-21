"""财经稿件读写与封面断行校验。"""

from __future__ import annotations

import json
import re
from pathlib import Path

from core.tools.topic_dedup import update

from .._constants import (
    DRAFT_FILE_NAME,
    MCP_ID,
    TOPIC_DEDUPLICATION_DAYS,
    production_dirs,
    production_run_id,
)
from .._errors import DraftNotFoundError, WorkflowStepError
from .parse_metadata import parse_metadata


def load_draft(path: str | Path, label: str) -> tuple[Path, dict]:
    resolved = Path(path).resolve()
    if not resolved.is_file():
        raise DraftNotFoundError(f"{label}不存在：{resolved}", {"path": str(resolved)})
    try:
        payload = json.loads(resolved.read_text(encoding="utf-8"))
    except (OSError, json.JSONDecodeError) as exc:
        raise WorkflowStepError(f"读取{label}失败：{resolved}。{exc}") from exc
    if not isinstance(payload, dict):
        raise WorkflowStepError(f"{label}必须是 JSON 对象：{resolved}")
    return resolved, payload


def _cover_lines(title: str, cover_lines: list[str] | None) -> list[str]:
    if not isinstance(cover_lines, list) or not cover_lines:
        raise WorkflowStepError("cover_lines 必须是 Agent 按语义断好的非空行列表")
    if len(cover_lines) > 3:
        raise WorkflowStepError("cover_lines 最多 3 行")
    lines = [str(item).strip() for item in cover_lines]
    if any(not item for item in lines):
        raise WorkflowStepError("cover_lines 里不能有空行")
    compact_title = re.sub(r"\s+", "", str(title or ""))
    compact_lines = re.sub(r"\s+", "", "".join(lines))
    if compact_lines != compact_title:
        raise WorkflowStepError(
            "cover_lines 去掉空白后必须拼回长标题 title，不要增删字",
            {"title": title, "cover_lines": lines},
        )
    return lines


def save_draft(
    topic: str,
    article: str,
    title: str,
    short_title: str,
    hashtags: list[str],
    cover_lines: list[str],
    database_path: Path,
    draft_path: str | Path | None = None,
) -> dict:
    normalized_topic = str(topic or "").strip()
    normalized_article = str(article or "").strip()
    if not normalized_topic:
        raise WorkflowStepError("topic 不能为空")
    if not normalized_article:
        raise WorkflowStepError("article 不能为空")
    if not isinstance(hashtags, list):
        raise WorkflowStepError("hashtags 必须是包含四个标签的列表")
    metadata_line = "|".join([str(title), str(short_title), *(str(item) for item in hashtags)])
    metadata = parse_metadata(metadata_line)
    normalized_cover_lines = _cover_lines(metadata["title"], cover_lines)
    if draft_path is not None:
        resolved_draft, existing = load_draft(draft_path, "待修改稿件")
        if normalized_topic != str(existing.get("topic") or "").strip():
            raise WorkflowStepError("修改已有稿件时不能更换话题；请重新开始一次财经制作")
        record = {"id": int(existing["topic_record_id"]), "topic": normalized_topic}
        run_id = str(existing["run_id"])
        cache_root = Path(existing["cache_dir"]).resolve()
        output_root = Path(existing["output_dir"]).resolve()
        target_draft_path = resolved_draft
    else:
        record = update(database_path, MCP_ID, normalized_topic, TOPIC_DEDUPLICATION_DAYS)
        run_id = production_run_id(record["id"])
        cache_root, output_root = production_dirs(run_id)
        target_draft_path = cache_root / DRAFT_FILE_NAME
    cache_root.mkdir(parents=True, exist_ok=True)
    output_root.mkdir(parents=True, exist_ok=True)
    draft = {
        "version": 1,
        "line": MCP_ID,
        "status": "awaiting_article_confirmation",
        "confirmation_required": "article",
        "database_path": str(database_path),
        "topic": record["topic"],
        "run_id": run_id,
        "topic_record_id": record["id"],
        "article": normalized_article,
        **metadata,
        "cover_lines": normalized_cover_lines,
        "cache_dir": str(cache_root),
        "output_dir": str(output_root),
        "draft_path": str(target_draft_path),
    }
    target_draft_path.write_text(json.dumps(draft, ensure_ascii=False, indent=2), encoding="utf-8")
    return draft
