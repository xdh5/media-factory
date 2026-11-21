"""制作语言词包时查询历史并校验新词比例。"""

from tools.database._errors import DatabaseError
from workflows.language_learning.parameters import WORD_HISTORY_DAYS, WORDS_PER_TASK, MINIMUM_NEW_WORDS
from workflows.language_learning.errors.exceptions import VocabularyHistoryError, VocabularyReuseError
from workflows.language_learning.tools.packs import normalize_english_word, _word_entries
from media_factory_mcp.language_learning.infrastructure.packs import list_recent_words as records_list_recent_words


def list_recent_words() -> list[str]:
    """返回 D1 最近 100 天使用过的英语词汇。"""
    try:
        return records_list_recent_words(WORD_HISTORY_DAYS)
    except DatabaseError as exc:
        raise VocabularyHistoryError(
            f"读取 Cloudflare D1 最近 {WORD_HISTORY_DAYS} 天单词历史失败：{exc.message}",
            exc.details,
        ) from exc


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
        recent = {normalize_english_word(word) for word in records_list_recent_words(WORD_HISTORY_DAYS)}
    except DatabaseError as exc:
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
