"""文生图稿件、分镜步骤。"""

from __future__ import annotations

import json
from pathlib import Path

from core.tools.run_cache import ConfirmationRequiredError as RunCacheConfirmationRequiredError
from core.tools.run_cache import clear_run
from core.tools.topic_history import get_topic, update

from ._constants import (
    DEFAULT_DATABASE_PATH,
    DRAFT_FILE_NAME,
    FORMAT_PROMPT_PATH,
    STORYBOARD_CONTEXT_FILE_NAME,
    production_dirs,
    production_run_id,
)
from ._errors import ConfirmationRequiredError, DraftNotFoundError, WorkflowStepError
from ._line import load_line
from .engine import assemble_article_prompt, compose_tts, parse_metadata, read_prompt, storyboard_prompt


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


def get_draft_context(line: str, database_path: str | Path | None = None) -> dict:
    selected = load_line(line)
    database = Path(database_path or DEFAULT_DATABASE_PATH).resolve()
    recent = get_topic(database, selected.id, selected.topic_deduplication_days)
    return {
        "line": selected.id,
        "workflow": selected.id,
        "deduplication_days": selected.topic_deduplication_days,
        "recent_topics": [item["topic"] for item in recent],
        "article_prompt_template": assemble_article_prompt(selected),
        "metadata_prompt": read_prompt(FORMAT_PROMPT_PATH),
        "visual_style": selected.visual_style,
        "bgm_id": selected.bgm_id,
        "matrixmedia_account_group": selected.matrixmedia_account_group,
        "next_tool": "text2image_save_draft",
    }


def save_draft(
    line: str,
    topic: str,
    article: str,
    title: str,
    short_title: str,
    hashtags: list[str],
    database_path: str | Path | None = None,
    draft_path: str | Path | None = None,
) -> dict:
    selected = load_line(line)
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
    database = Path(database_path or DEFAULT_DATABASE_PATH).resolve()
    if draft_path is not None:
        resolved_draft, existing = load_draft(draft_path, "待修改稿件")
        if str(existing.get("line") or "").strip() != selected.id:
            raise WorkflowStepError("修改已有稿件时不能更换业务线")
        if normalized_topic != str(existing.get("topic") or "").strip():
            raise WorkflowStepError("修改已有稿件时不能更换话题；请重新开始一次文生图工作流")
        record = {"id": int(existing["topic_record_id"]), "topic": normalized_topic}
        run_id = str(existing["run_id"])
        cache_root = Path(existing["cache_dir"]).resolve()
        output_root = Path(existing["output_dir"]).resolve()
        target_draft_path = resolved_draft
    else:
        record = update(database, selected.id, normalized_topic, selected.topic_deduplication_days)
        run_id = production_run_id(record["id"])
        _run_dir, cache_root, output_root = production_dirs(selected.id, run_id)
        target_draft_path = cache_root / DRAFT_FILE_NAME
    cache_root.mkdir(parents=True, exist_ok=True)
    output_root.mkdir(parents=True, exist_ok=True)
    draft = {
        "version": 1,
        "line": selected.id,
        "status": "awaiting_article_confirmation",
        "confirmation_required": "article",
        "database_path": str(database),
        "topic": record["topic"],
        "run_id": run_id,
        "topic_record_id": record["id"],
        "article": normalized_article,
        **metadata,
        "cache_dir": str(cache_root),
        "output_dir": str(output_root),
        "draft_path": str(target_draft_path),
    }
    target_draft_path.write_text(json.dumps(draft, ensure_ascii=False, indent=2), encoding="utf-8")
    return draft


def prepare_storyboard(draft_path: str | Path, *, user_confirmed: bool) -> dict:
    if user_confirmed is not True:
        raise ConfirmationRequiredError("必须先获得用户对完整稿件的明确确认")
    resolved_draft, draft = load_draft(draft_path, "待确认稿件")
    for key in ("article", "cache_dir", "topic_record_id", "line"):
        if not draft.get(key):
            raise WorkflowStepError(f"待确认稿件缺少字段：{key}")
    line = load_line(str(draft["line"]))
    cache_root = Path(draft["cache_dir"]).resolve()
    tts_result = compose_tts(line, str(draft["article"]), cache_root)
    prompt = storyboard_prompt(line, tts_result["timeline"])
    context_path = cache_root / STORYBOARD_CONTEXT_FILE_NAME
    context = {
        "status": "awaiting_storyboard",
        "line": line.id,
        "draft_path": str(resolved_draft),
        "storyboard_prompt": prompt,
        "timeline": tts_result["timeline"],
        "tts_path": tts_result["output_path"],
        "tts_loudness": tts_result["loudness"],
        "next_tool": "text2image_prepare_images",
    }
    context_path.write_text(json.dumps(context, ensure_ascii=False, indent=2), encoding="utf-8")
    context["context_path"] = str(context_path)
    return context


def clear_text2image_run(line: str, run_id: str, *, confirmed: bool) -> dict:
    selected = load_line(line)
    try:
        return clear_run(selected.id, run_id, confirmed=confirmed)
    except RunCacheConfirmationRequiredError as exc:
        raise ConfirmationRequiredError(str(exc)) from exc
    except Exception as exc:
        raise WorkflowStepError(str(exc)) from exc
