"""通过 Cloudflare D1 保存单词历史，并校验最近词汇复用比例。"""

from __future__ import annotations

import json
import re
import unicodedata

from core.tools.cloudflare_data import (
    CloudflareDataConflictError,
    CloudflareDataError,
    list_recent_words as cloudflare_list_recent_words,
    validate_and_record_words as cloudflare_validate_and_record_words,
)

from .._constants import (
    MINIMUM_NEW_WORDS,
    SUPPORTED_LEARNING_MODES,
    WORD_HISTORY_DAYS,
    WORDS_PER_TASK,
    WORKFLOW_ID,
)
from .._errors import VocabularyHistoryError, VocabularyReuseError


def _normalize_word(value: str) -> str:
    normalized = unicodedata.normalize("NFKC", str(value or "")).casefold().replace("’", "'")
    return re.sub(r"\s+", " ", normalized).strip()


def list_recent_words() -> list[str]:
    """返回 D1 最近 100 天使用过的英语词汇。"""
    try:
        return cloudflare_list_recent_words(WORD_HISTORY_DAYS)
    except CloudflareDataError as exc:
        raise VocabularyHistoryError(
            f"读取 Cloudflare D1 最近 {WORD_HISTORY_DAYS} 天单词历史失败：{exc.message}",
            exc.details,
        ) from exc


def _word_entries(words_by_mode: dict) -> list[dict]:
    entries: dict[str, dict] = {}
    for mode in SUPPORTED_LEARNING_MODES:
        for item in words_by_mode.get(mode) or []:
            english = str(item.get("english") or "").strip()
            normalized = _normalize_word(english)
            if not normalized:
                raise VocabularyHistoryError(f"{mode} 词表存在空的英语单词")
            entry = entries.setdefault(
                normalized,
                {"english": english, "normalized_english": normalized, "modes": {}},
            )
            entry["modes"][mode] = dict(item)
    if len(entries) != WORDS_PER_TASK:
        raise VocabularyHistoryError(
            f"单词历史每次必须记录 {WORDS_PER_TASK} 个不同英语词，现在是 {len(entries)} 个"
        )
    return list(entries.values())


def validate_and_record_words(*, run_id: str, topic: str, words_by_mode: dict) -> dict:
    """由 Worker 在 D1 中原子校验新词比例并记录全部单词。"""
    rid = str(run_id or "").strip()
    clean_topic = str(topic or "").strip()
    if not rid or not clean_topic:
        raise VocabularyHistoryError("记录单词历史时 run_id 和 topic 不能为空")
    if re.fullmatch(r"run-(\d{6,})", rid) is None:
        raise VocabularyHistoryError(f"run_id 格式不正确：{rid}")
    entries = _word_entries(words_by_mode)
    payload_entries = [
        {
            "english": entry["english"],
            "normalized_english": entry["normalized_english"],
            "word_json": json.dumps(entry, ensure_ascii=False, separators=(",", ":")),
        }
        for entry in entries
    ]
    try:
        return cloudflare_validate_and_record_words(
            workflow=WORKFLOW_ID,
            run_id=rid,
            topic=clean_topic,
            entries=payload_entries,
            history_days=WORD_HISTORY_DAYS,
            minimum_new_words=MINIMUM_NEW_WORDS,
        )
    except CloudflareDataConflictError as exc:
        if exc.remote_code == "VOCABULARY_REUSE_LIMIT":
            raise VocabularyReuseError(exc.message, exc.details) from exc
        raise VocabularyHistoryError(exc.message, exc.details) from exc
    except CloudflareDataError as exc:
        raise VocabularyHistoryError(
            f"保存 Cloudflare D1 单词历史失败：{exc.message}",
            exc.details,
        ) from exc

