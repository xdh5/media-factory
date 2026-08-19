"""语言学习 MCP 对外步骤。"""

from __future__ import annotations

from pathlib import Path

from core.tools.image import ImageGenerationError, prepare_agent_image_tasks, save_agent_image_tasks
from core.tools.run_cache import ConfirmationRequiredError as RunCacheConfirmationRequiredError
from core.tools.run_cache import clear_run
from core.tools.topic_history import DuplicateTopicError, get_topic, update

from .._constants import (
    DEFAULT_DATABASE_PATH,
    SUBJECT_SHEET_IMAGE_ID,
    SUBJECT_SHEET_RADIO,
    SUBJECT_SHEET_SIZE_TEXT,
    TOPIC_DEDUPLICATION_DAYS,
    WORKFLOW_ID,
    production_dirs,
    production_run_id,
)
from .._errors import ConfirmationRequiredError, LanguageLearningError
from .vocabulary import build_subject_sheet_prompt, build_vocabulary_prompt


def get_topics(database_path: str | Path | None = None) -> dict:
    database = Path(database_path or DEFAULT_DATABASE_PATH).resolve()
    recent = get_topic(database, WORKFLOW_ID, TOPIC_DEDUPLICATION_DAYS)
    return {
        "workflow": WORKFLOW_ID,
        "deduplication_days": TOPIC_DEDUPLICATION_DAYS,
        "recent_topics": [item["topic"] for item in recent],
        "next_tool": "language_learning_build_vocabulary_prompt",
    }


def occupy_topic_and_build_prompt(
    topic: str,
    learning_modes: list[str],
    database_path: str | Path | None = None,
) -> dict:
    database = Path(database_path or DEFAULT_DATABASE_PATH).resolve()
    try:
        record = update(database, WORKFLOW_ID, topic, TOPIC_DEDUPLICATION_DAYS)
    except DuplicateTopicError as exc:
        raise LanguageLearningError(str(exc), exc.details) from exc
    result = build_vocabulary_prompt(record["topic"], learning_modes)
    run_id = production_run_id(record["id"])
    run_dir, cache_root, output_root = production_dirs(run_id)
    cache_root.mkdir(parents=True, exist_ok=True)
    output_root.mkdir(parents=True, exist_ok=True)
    return {
        **result,
        "topic_record_id": record["id"],
        "run_id": run_id,
        "cache_dir": str(cache_root),
        "output_dir": str(output_root),
        "run_dir": str(run_dir),
        "next_tool": "language_learning_parse_vocabulary_response",
    }


def prepare_images(topic: str, words: list[dict], run_id: str, force_images: bool = False) -> dict:
    if not isinstance(force_images, bool):
        raise LanguageLearningError("force_images 必须是布尔值")
    sheet = build_subject_sheet_prompt(topic, words)
    _run_dir, cache_root, _output_root = production_dirs(run_id)
    cache_root = cache_root / "agent-images"
    try:
        result = prepare_agent_image_tasks(
            [{"image_id": SUBJECT_SHEET_IMAGE_ID, "kind": "image", "prompt": sheet["prompt"]}],
            None,
            SUBJECT_SHEET_RADIO,
            SUBJECT_SHEET_SIZE_TEXT,
            cache_root,
            force_images=force_images,
            metadata={"workflow": "language_learning", "topic": sheet["topic"], "run_id": run_id},
        )
    except ImageGenerationError as exc:
        raise LanguageLearningError(exc.message, exc.details) from exc
    next_tool = (
        "language_learning_save_images"
        if any(task.get("needs_generation") for task in result.get("tasks") or [])
        else "language_learning_submit_images"
    )
    return {**result, "topic": sheet["topic"], "run_id": run_id, "next_tool": next_tool}


def save_images(context_path: str, images: list[dict]) -> dict:
    try:
        result = save_agent_image_tasks(context_path, images)
    except ImageGenerationError as exc:
        raise LanguageLearningError(exc.message, exc.details) from exc
    next_tool = (
        "language_learning_submit_images"
        if not result.get("pending_image_ids")
        else "language_learning_save_images"
    )
    return {**result, "next_tool": next_tool}


def clear_language_learning_run(run_id: str, *, confirmed: bool) -> dict:
    try:
        return clear_run(WORKFLOW_ID, run_id, confirmed=confirmed)
    except RunCacheConfirmationRequiredError as exc:
        raise ConfirmationRequiredError(str(exc)) from exc
