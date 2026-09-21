"""心理测试稿件校验与保存。"""

from __future__ import annotations

import json
from pathlib import Path

from .._constants import DRAFT_FILE_NAME, MCP_ID, production_dirs, production_run_id
from .._errors import WorkflowStepError
from .parse_metadata import parse_metadata

QUIZ_CATEGORIES = {"finance", "success", "human_nature"}
QUIZ_ARTICLE_MIN_LENGTH = 300
QUIZ_KEYS = ("a", "b", "c", "d")


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


def validate_quiz(quiz: dict, article: str) -> dict:
    if not isinstance(quiz, dict):
        raise WorkflowStepError("quiz 必须是对象")
    category = str(quiz.get("category") or "").strip()
    if category not in QUIZ_CATEGORIES:
        raise WorkflowStepError("quiz.category 必须从 finance、success、human_nature 中选择")
    scene_title = str(quiz.get("scene_title") or "").strip()
    scenario = str(quiz.get("scenario") or "").strip()
    if not scene_title or not scenario:
        raise WorkflowStepError("quiz.scene_title 和 quiz.scenario 不能为空")
    options = quiz.get("options")
    results = quiz.get("results")
    if not isinstance(options, dict) or set(options) != set(QUIZ_KEYS):
        raise WorkflowStepError("quiz.options 必须完整包含 a、b、c、d")
    if not isinstance(results, dict) or set(results) != set(QUIZ_KEYS):
        raise WorkflowStepError("quiz.results 必须完整包含 a、b、c、d")
    normalized_options = {key: str(options[key] or "").strip() for key in QUIZ_KEYS}
    normalized_results = {key: str(results[key] or "").strip() for key in QUIZ_KEYS}
    if any(not value for value in [*normalized_options.values(), *normalized_results.values()]):
        raise WorkflowStepError("四个选项和四个结果都不能为空")
    if len(set(normalized_options.values())) != 4 or len(set(normalized_results.values())) != 4:
        raise WorkflowStepError("四个选项和四个结果必须彼此不同")
    keywords = quiz.get("video_keywords")
    if not isinstance(keywords, list) or not 1 <= len(keywords) <= 20:
        raise WorkflowStepError("quiz.video_keywords 必须包含1～20个英文视频检索词")
    normalized_keywords = [str(item or "").strip() for item in keywords]
    if any(not item for item in normalized_keywords):
        raise WorkflowStepError("quiz.video_keywords 不能包含空字符串")
    normalized_article = str(article or "").strip()
    article_length = len("".join(normalized_article.split()))
    if article_length < QUIZ_ARTICLE_MIN_LENGTH:
        raise WorkflowStepError(
            f"心理测试正文去除空白后不得少于 {QUIZ_ARTICLE_MIN_LENGTH} 个字符，当前为 {article_length} 个字符"
        )
    long_lines = [
        (index, len(line.strip()))
        for index, line in enumerate(normalized_article.splitlines(), 1)
        if len(line.strip()) > 20
    ]
    if long_lines:
        raise WorkflowStepError("心理测试正文每行不得超过20字", {"long_lines": long_lines})
    compact_article = "".join(normalized_article.split())
    for key in QUIZ_KEYS:
        if "".join(normalized_options[key].split()) not in compact_article:
            raise WorkflowStepError(f"正文必须逐字包含选项 {key.upper()}")
        if "".join(normalized_results[key].split()) not in compact_article:
            raise WorkflowStepError(f"正文必须逐字包含结果 {key.upper()}")
    return {
        "category": category,
        "scene_title": scene_title,
        "scenario": scenario,
        "options": normalized_options,
        "results": normalized_results,
        "video_keywords": normalized_keywords,
        "article": normalized_article,
    }


def validate_draft_fields(
    *, quiz: dict, article: str, title: str, short_title: str,
    hashtags: list[str], cover_lines: list[str], cover_highlights: list[str],
) -> dict:
    normalized_quiz = validate_quiz(quiz, article)
    metadata = parse_metadata("|".join([str(title), str(short_title), *(str(item) for item in hashtags)]))
    return {
        "quiz": normalized_quiz,
        "metadata": metadata,
        "cover_lines": _cover_lines(cover_lines),
        "cover_highlights": _cover_highlights(metadata["title"], cover_highlights),
    }


def save_quiz_draft(
    *, topic: str, quiz: dict, article: str, title: str, short_title: str,
    hashtags: list[str], cover_lines: list[str], cover_highlights: list[str],
    publish_date: str, topic_record: dict, draft_path: str | Path | None = None,
) -> dict:
    normalized_topic = str(topic or "").strip()
    if not normalized_topic:
        raise WorkflowStepError("topic 不能为空")
    validated = validate_draft_fields(
        quiz=quiz, article=article, title=title, short_title=short_title,
        hashtags=hashtags, cover_lines=cover_lines, cover_highlights=cover_highlights,
    )
    if draft_path is None:
        run_id = production_run_id(publish_date)
        cache_root, output_root = production_dirs(run_id)
        target = cache_root / DRAFT_FILE_NAME
        record_id = int(topic_record["id"])
    else:
        resolved, existing = load_draft(draft_path, "待修改心理测试稿件")
        if normalized_topic != str(existing.get("topic") or "").strip():
            raise WorkflowStepError("修改已有心理测试稿件时不能更换话题")
        run_id = str(existing["run_id"])
        cache_root = Path(existing["cache_dir"]).resolve()
        output_root = Path(existing["output_dir"]).resolve()
        target = resolved
        record_id = int(existing["topic_record_id"])
    cache_root.mkdir(parents=True, exist_ok=True)
    output_root.mkdir(parents=True, exist_ok=True)
    draft = {
        "version": 1,
        "line": MCP_ID,
        "content_kind": "scenario_quiz",
        "status": "ready_for_production",
        "topic": normalized_topic,
        "run_id": run_id,
        "topic_record_id": record_id,
        "database_status": "pending_publish",
        "publish_date": str(publish_date).strip(),
        "quiz": validated["quiz"],
        "article": validated["quiz"]["article"],
        **validated["metadata"],
        "cover_lines": validated["cover_lines"],
        "cover_highlights": validated["cover_highlights"],
        "cache_dir": str(cache_root),
        "output_dir": str(output_root),
        "draft_path": str(target),
    }
    target.write_text(json.dumps(draft, ensure_ascii=False, indent=2), encoding="utf-8")
    return draft
