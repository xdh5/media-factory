"""读取 Cloudflare D1 单词历史并校验复用比例，发布清单携带待入库词表。"""

from __future__ import annotations

import json
import re
import unicodedata

from core.tools.cloudflare_data import CloudflareDataError, list_recent_words as cloudflare_list_recent_words

from .._constants import (
    MINIMUM_NEW_WORDS,
    SUPPORTED_LEARNING_MODES,
    WORD_HISTORY_DAYS,
    WORDS_PER_TASK,
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


def build_database_word_entries(words_by_mode: dict) -> list[dict]:
    """生成随发布清单传递、待用户点击发布后入库的单词数据。"""
    return [
        {
            "english": entry["english"],
            "normalized_english": entry["normalized_english"],
            "word_json": json.dumps(entry, ensure_ascii=False, separators=(",", ":")),
        }
        for entry in _word_entries(words_by_mode)
    ]


def validate_words(*, run_id: str, topic: str, words_by_mode: dict) -> dict:
    """生产阶段只读取 D1 校验新词比例，不写入任何话题或单词。"""
    rid = str(run_id or "").strip()
    clean_topic = str(topic or "").strip()
    if not rid or not clean_topic:
        raise VocabularyHistoryError("校验单词历史时 run_id 和 topic 不能为空")
    if re.fullmatch(r"run-(\d{6,})", rid) is None:
        raise VocabularyHistoryError(f"run_id 格式不正确：{rid}")
    entries = _word_entries(words_by_mode)
    try:
        recent = {_normalize_word(word) for word in cloudflare_list_recent_words(WORD_HISTORY_DAYS)}
    except CloudflareDataError as exc:
        raise VocabularyHistoryError(
            f"读取 Cloudflare D1 单词历史失败：{exc.message}",
            exc.details,
        ) from exc
    repeated_words = [entry["english"] for entry in entries if entry["normalized_english"] in recent]
    new_word_count = len(entries) - len(repeated_words)
    if new_word_count < MINIMUM_NEW_WORDS:
        raise VocabularyReuseError(
            f"本次只有 {new_word_count} 个新词；{WORDS_PER_TASK} 个单词中至少需要 "
            f"{MINIMUM_NEW_WORDS} 个未在最近 {WORD_HISTORY_DAYS} 天使用",
            {
                "history_days": WORD_HISTORY_DAYS,
                "minimum_new_words": MINIMUM_NEW_WORDS,
                "new_word_count": new_word_count,
                "repeated_word_count": len(repeated_words),
                "repeated_words": repeated_words,
            },
        )
    return {
        "recorded": False,
        "pending_publish": True,
        "run_id": rid,
        "word_count": len(entries),
        "new_word_count": new_word_count,
        "repeated_word_count": len(repeated_words),
        "repeated_words": repeated_words,
        "history_days": WORD_HISTORY_DAYS,
        "minimum_new_words": MINIMUM_NEW_WORDS,
    }
