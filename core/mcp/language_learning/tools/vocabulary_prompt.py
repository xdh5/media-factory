"""词表 Prompt 生成与严格解析。"""

from __future__ import annotations

import re
from pathlib import Path

from .._constants import MINIMUM_NEW_WORDS, SUPPORTED_LEARNING_MODES, WORD_HISTORY_DAYS, WORDS_PER_TASK
from .._errors import InvalidVocabularyError

_PROMPTS_DIR = Path(__file__).resolve().parent.parent / "prompts"


def _modes(value: list[str]) -> list[str]:
    modes = list(dict.fromkeys(str(item).strip() for item in value))
    if not modes or any(item not in SUPPORTED_LEARNING_MODES for item in modes):
        raise InvalidVocabularyError("请选择至少一个受支持的语言学习方向", {"supported_modes": list(SUPPORTED_LEARNING_MODES)})
    return [item for item in SUPPORTED_LEARNING_MODES if item in modes]


def _read_prompt(name: str) -> str:
    path = _PROMPTS_DIR / name
    if not path.is_file():
        raise InvalidVocabularyError(f"Prompt 模板不存在：{path}")
    return path.read_text(encoding="utf-8").strip()


def build_visual_validation_prompt() -> dict:
    """返回给宿主 Agent 使用的主题图视觉验收 Prompt。"""
    return {
        "system_prompt": _read_prompt("visual-validation-system.md"),
        "user_prompt": _read_prompt("visual-validation-user.md"),
        "response_format": "json",
        "next_tool": "language_learning_validate_subject_sheet",
    }


def _format(modes: list[str]) -> tuple[str, list[str]]:
    if modes == ["en-zh"]:
        return "序号｜英语｜中文｜拼音", ["english", "chinese", "romanization"]
    if modes == ["en-ko"]:
        return "序号｜英语｜中文｜韩语｜韩语罗马音", ["english", "chinese", "korean", "romanization"]
    return "序号｜英语｜中文｜拼音｜韩语｜韩语罗马音", ["english", "chinese", "chinese_romanization", "korean", "korean_romanization"]


def _language_rule(modes: list[str]) -> str:
    if modes == ["en-zh"]:
        return "提供简体中文和规范汉语拼音，拼音带声调并按音节空格分隔。"
    if modes == ["en-ko"]:
        return "提供简体中文释义、韩语和适合初学者的韩语罗马音；韩语罗马音按音节用连字符分隔。"
    return (
        "同时提供中文和韩语，同一行必须表达同一个英语概念；"
        "中文拼音必须带声调并按音节用空格分隔；"
        "韩语罗马音必须按每个韩文音节用英文半角连字符“-”分隔。"
    )


def _normalize_korean_romanization(korean: str, romanization: str, row_index: int) -> str:
    """统一连字符并强制韩语罗马音与韩文音节逐一对应。"""
    normalized = re.sub(r"[‐‑‒–—−]", "-", str(romanization or "").strip())
    syllable_count = sum("가" <= character <= "힣" for character in str(korean or ""))
    parts = [part.strip() for part in normalized.split("-")]
    if syllable_count and (len(parts) != syllable_count or any(not part for part in parts)):
        raise InvalidVocabularyError(
            f"第 {row_index} 行韩语罗马音必须按 {syllable_count} 个韩文音节用半角连字符分隔："
            f"{korean}｜{romanization}"
        )
    return "-".join(parts)


def build_vocabulary_prompt(topic: str, learning_modes: list[str], recent_words: list[str] | None = None) -> dict:
    modes = _modes(learning_modes)
    clean_topic = str(topic or "").strip()
    if re.fullmatch(r"[A-Za-z]+", clean_topic) is None:
        raise InvalidVocabularyError("语言学习主题必须是一个不含空格的英文单词")
    table_header, _ = _format(modes)
    history = [str(word).strip() for word in (recent_words or []) if str(word).strip()]
    if history:
        recent_words_rule = (
            f"最近 {WORD_HISTORY_DAYS} 天已经使用过的英语单词如下：\n"
            f"{', '.join(history)}\n"
            f"本次 {WORDS_PER_TASK} 个单词中，至少 {MINIMUM_NEW_WORDS} 个不得出现在上面的历史词库中。"
        )
    else:
        recent_words_rule = f"最近 {WORD_HISTORY_DAYS} 天暂无历史单词，本次全部单词都视为新词。"
    user_prompt = _read_prompt("vocabulary-user.md").format(
        topic=clean_topic,
        language_rule=_language_rule(modes),
        recent_words_rule=recent_words_rule,
        table_header=table_header,
    )
    return {
        "topic": clean_topic,
        "learning_modes": modes,
        "user_prompt": user_prompt,
        "recent_words": history,
        "word_history_days": WORD_HISTORY_DAYS,
        "minimum_new_words": MINIMUM_NEW_WORDS,
    }


def build_subject_sheet_prompt(topic: str, words: list[dict]) -> dict:
    clean_topic = str(topic or "").strip()
    if re.fullmatch(r"[A-Za-z]+", clean_topic) is None:
        raise InvalidVocabularyError("语言学习主题必须是一个不含空格的英文单词")
    if len(words) != WORDS_PER_TASK:
        raise InvalidVocabularyError(f"主体图需要 {WORDS_PER_TASK} 个单词，现在只有 {len(words)} 个")
    word_list = "\n".join(
        f"{index}. {str(word.get('english') or '').strip()}"
        for index, word in enumerate(words, 1)
    )
    if any(not line.split(". ", 1)[-1] for line in word_list.splitlines()):
        raise InvalidVocabularyError("每个单词都必须有 english 字段")
    prompt = _read_prompt("subject-sheet.md").format(topic=clean_topic, word_list=word_list)
    return {"topic": clean_topic, "subject_sheet_prompt": prompt}


def parse_vocabulary_response(content: str, learning_modes: list[str]) -> dict:
    modes = _modes(learning_modes)
    _, fields = _format(modes)
    topic_english = ""
    rows: list[list[str]] = []
    for raw in str(content or "").replace("```text", "").replace("```", "").splitlines():
        line = raw.strip()
        if not line:
            continue
        parts = [part.strip() for part in re.split(r"[|｜]", line)]
        label = parts[0].strip("[]【】*#_：: ") if parts else ""
        if label in {"英文主题", "主题英文"} and len(parts) >= 2:
            topic_english = parts[1].strip("[]【】*#_：: ")
        elif len(parts) == len(fields) + 1 and parts[0].isdigit():
            rows.append(parts[1:])
        elif not topic_english:
            topic_match = re.match(
                r"^(?:\*{0,2})?(?:英文主题|主题英文|English Topic|English Theme)(?:\*{0,2})?\s*[：:]\s*(.+?)\s*$",
                line,
                flags=re.IGNORECASE,
            )
            if topic_match:
                topic_english = topic_match.group(1).strip("[]【】*#_：: ")
    if not topic_english:
        raise InvalidVocabularyError("词表缺少“英文主题｜...”行")
    if re.fullmatch(r"[A-Za-z]+", topic_english) is None:
        raise InvalidVocabularyError("英文主题必须是一个不含空格的英文单词")
    if len(rows) != WORDS_PER_TASK:
        raise InvalidVocabularyError(f"词表必须正好有 {WORDS_PER_TASK} 行，现在解析到 {len(rows)} 行")
    normalized, seen = [], set()
    for index, values in enumerate(rows, 1):
        item = dict(zip(fields, values))
        if any(not value for value in item.values()):
            raise InvalidVocabularyError(f"第 {index} 行存在空字段")
        if "en-ko" in modes:
            romanization_field = "korean_romanization" if "korean_romanization" in item else "romanization"
            item[romanization_field] = _normalize_korean_romanization(
                item["korean"],
                item[romanization_field],
                index,
            )
        key = item["english"].casefold()
        if key in seen:
            raise InvalidVocabularyError(f"英语单词重复：{item['english']}")
        seen.add(key)
        normalized.append(item)
    result: dict = {"_topic_english": topic_english}
    if "en-zh" in modes:
        result["en-zh"] = [{"english": item["english"], "chinese": item["chinese"], "korean": item["chinese"], "romanization": item.get("chinese_romanization", item.get("romanization", ""))} for item in normalized]
    if "en-ko" in modes:
        result["en-ko"] = [{"english": item["english"], "chinese": item["chinese"], "korean": item["korean"], "romanization": item.get("korean_romanization", item.get("romanization", ""))} for item in normalized]
    return result
