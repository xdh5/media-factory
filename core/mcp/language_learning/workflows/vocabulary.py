"""主题占用与词表生成校验。"""

from __future__ import annotations

import re


from ..infrastructure import (
    list_language_learning_pack_topics,
    get_topic,
    list_production_outputs,
)

from ..config import (
    MINIMUM_NEW_WORDS,
    TOPIC_DEDUPLICATION_DAYS,
    WORD_HISTORY_DAYS,
    WORKFLOW_ID,
    production_dirs,
    production_run_id,
)
from ..errors import LanguageLearningError
from ..services.prompt_service import (
    build_topic_prompt,
    build_vocabulary_prompt, parse_vocabulary_response, validate_topic_response,
)
from ..services.vocabulary import list_recent_words, validate_words
from .tasks import _map_error


def language_learning_get_topic_generation_prompt(recent_topics: list[str], requested_topic: str = "", feedback: str = "") -> dict:
    """返回宿主 Agent 与 GitHub Runner 共用的主题生成 Prompt。"""
    try:
        return build_topic_prompt(recent_topics, requested_topic, feedback)
    except Exception as exc:
        raise _map_error(exc) from exc


def language_learning_validate_topic_response(response_text: str, recent_topics: list[str]) -> dict:
    """统一校验宿主 Agent 生成的英文主题。"""
    try:
        return validate_topic_response(response_text, recent_topics)
    except Exception as exc:
        raise _map_error(exc) from exc


def language_learning_get_topics() -> dict:
    """返回最近 30 天已占用主题及所有已入库预制图包主题。"""
    try:
        recent = get_topic(WORKFLOW_ID, TOPIC_DEDUPLICATION_DAYS)
        recent_words = list_recent_words()
        return {
            "workflow": WORKFLOW_ID,
            "deduplication_days": TOPIC_DEDUPLICATION_DAYS,
            "recent_topics": [item["topic"] for item in recent],
            "pack_topics": list_language_learning_pack_topics(),
            "recent_words": recent_words,
            "word_history_days": WORD_HISTORY_DAYS,
            "minimum_new_words": MINIMUM_NEW_WORDS,
            "supported_learning_modes": ["en-zh", "en-ko"],
        }
    except Exception as exc:
        raise _map_error(exc) from exc


def language_learning_occupy_topic(
    topic: str,
    learning_modes: list[str],
    publish_date: str,
    redo_existing_run: bool = False,
) -> dict:
    """按北京时间计划发布日期创建生产目录；正式话题仅在发布后写入 D1。"""
    modes = [str(item).strip() for item in learning_modes if str(item).strip()]
    if not modes:
        raise LanguageLearningError("learning_modes 不能为空")
    clean_topic = str(topic or "").strip()
    if re.fullmatch(r"[A-Za-z]+", clean_topic) is None:
        raise LanguageLearningError("语言学习 topic 必须是一个不含空格的英文单词")
    try:
        run_id = production_run_id(publish_date)
    except ValueError as exc:
        raise LanguageLearningError(str(exc)) from exc
    recent = get_topic(WORKFLOW_ID, TOPIC_DEDUPLICATION_DAYS)
    is_recent = clean_topic.casefold() in {
        str(item.get("topic") or "").strip().casefold() for item in recent
    }
    if is_recent and not redo_existing_run:
        raise LanguageLearningError(f"语言学习 topic 最近 {TOPIC_DEDUPLICATION_DAYS} 天已经发布：{clean_topic}")
    if redo_existing_run:
        existing = list_production_outputs(
            publish_date=str(publish_date).strip(),
            business_line=WORKFLOW_ID,
        )
        if not any(str(item.get("run_id") or "") == run_id for item in existing):
            raise LanguageLearningError(
                f"找不到 {run_id} 的既有语言学习产物，不能使用 redo_existing_run"
            )
    record_id = int(run_id.removeprefix("run-"))
    cache_root, output_root = production_dirs(run_id)
    cache_root.mkdir(parents=True, exist_ok=True)
    output_root.mkdir(parents=True, exist_ok=True)
    return {
        "topic": clean_topic,
        "learning_modes": modes,
        "topic_record_id": record_id,
        "database_status": "pending_publish",
        "publish_date": str(publish_date).strip(),
        "run_id": run_id,
        "cache_dir": str(cache_root),
        "output_dir": str(output_root),
        "redo_existing_run": bool(redo_existing_run),
    }


def language_learning_build_vocabulary_prompt(
    topic: str,
    learning_modes: list[str],
) -> dict:
    """返回词表生成 Prompt；Agent 按原样生成纯文本后交给 parse_vocabulary_response。"""
    try:
        return build_vocabulary_prompt(topic, learning_modes, list_recent_words())
    except Exception as exc:
        raise _map_error(exc) from exc


def language_learning_parse_vocabulary_response(
    response_text: str,
    learning_modes: list[str],
    topic: str,
    run_id: str,
    redo_existing_run: bool = False,
) -> dict:
    """严格解析词表并校验最近 100 天新词比例；发布时才记录单词。"""
    try:
        parsed = parse_vocabulary_response(response_text, learning_modes)
        if str(parsed.get("_topic_english") or "").casefold() != str(topic).strip().casefold():
            raise LanguageLearningError("词表英文主题必须与本次单词 TOPIC 完全一致")
        if redo_existing_run:
            raw_date = str(run_id).removeprefix("run-")
            publish_date = f"{raw_date[:4]}-{raw_date[4:6]}-{raw_date[6:8]}"
            existing = list_production_outputs(
                publish_date=publish_date,
                business_line=WORKFLOW_ID,
            )
            if not any(str(item.get("run_id") or "") == run_id for item in existing):
                raise LanguageLearningError(
                    f"找不到 {run_id} 的既有语言学习产物，不能复用旧词表"
                )
            history = {"status": "reused_existing_words", "run_id": run_id}
        else:
            history = validate_words(
                run_id=run_id,
                topic=topic,
                words_by_mode=parsed,
            )
        return {**parsed, "word_history": history}
    except Exception as exc:
        raise _map_error(exc) from exc
