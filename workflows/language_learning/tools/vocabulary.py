"""词表 Prompt 构造与严格解析。"""

import re
from pathlib import Path

from .._constants import CARD_GRID_COLUMNS, CARD_GRID_ROWS, PROMPT_ROOT, SUBJECT_SHEET_HEIGHT, SUBJECT_SHEET_WIDTH, SUPPORTED_LEARNING_MODES, WORDS_PER_TASK
from .._errors import InvalidVocabularyError


def _modes(value: list[str]) -> list[str]:
    modes = list(dict.fromkeys(str(item).strip() for item in value))
    if not modes or any(item not in SUPPORTED_LEARNING_MODES for item in modes):
        raise InvalidVocabularyError("请选择至少一个受支持的语言学习方向", {"supported_modes": list(SUPPORTED_LEARNING_MODES)})
    return [item for item in SUPPORTED_LEARNING_MODES if item in modes]


def _prompt(name: str) -> str:
    path = PROMPT_ROOT / name
    try:
        return path.read_text(encoding="utf-8").strip()
    except OSError as exc:
        raise InvalidVocabularyError(f"语言学习 Prompt 文件不可用：{name}") from exc


def _format(modes: list[str]) -> tuple[str, list[str]]:
    if modes == ["en-zh"]:
        return "序号｜英语｜中文｜拼音", ["english", "chinese", "romanization"]
    if modes == ["en-ko"]:
        return "序号｜英语｜中文｜韩语｜韩语罗马音", ["english", "chinese", "korean", "romanization"]
    return "序号｜英语｜中文｜拼音｜韩语｜韩语罗马音", ["english", "chinese", "chinese_romanization", "korean", "korean_romanization"]


def build_vocabulary_prompt(topic: str, learning_modes: list[str]) -> dict:
    clean_topic = str(topic or "").strip()
    if not clean_topic:
        raise InvalidVocabularyError("请先填写主题")
    modes = _modes(learning_modes)
    table_header, _ = _format(modes)
    language_rule = (
        "同时提供中文和韩语；同一行必须表达同一个英语概念。" if len(modes) == 2 else
        ("提供简体中文和规范汉语拼音，拼音带声调并按音节空格分隔。" if modes == ["en-zh"] else "提供简体中文释义、韩语和适合初学者的韩语罗马音；韩语罗马音按音节用连字符分隔。")
    )
    return {"topic": clean_topic, "learning_modes": modes, "user_prompt": _prompt("vocabulary-user.md").format(topic=clean_topic, language_rule=language_rule, table_header=table_header)}


def build_subject_sheet_prompt(topic: str, words: list[dict]) -> dict:
    """内部使用：生成主体图 Prompt，供 generate_image 组装任务，不作为 MCP 生图入口。"""
    if len(words) != WORDS_PER_TASK:
        raise InvalidVocabularyError(f"生成主体图前必须提供正好 {WORDS_PER_TASK} 个单词")
    names = []
    for index, word in enumerate(words, 1):
        english = str(word.get("english") or "").strip()
        if not english:
            raise InvalidVocabularyError(f"第 {index} 个单词缺少 english 字段")
        names.append(f"{index}. {english}")
    word_list = "\n".join(names)
    prompt = _prompt("subject-sheet.md").format(
        topic=str(topic or "").strip(),
        word_list=word_list,
    )
    return {
        "topic": str(topic or "").strip(),
        "canvas": {"width": SUBJECT_SHEET_WIDTH, "height": SUBJECT_SHEET_HEIGHT},
        "grid": {"rows": CARD_GRID_ROWS, "columns": CARD_GRID_COLUMNS},
        "prompt": prompt,
    }


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
        label = parts[0].strip("[]：: ") if parts else ""
        if label in {"英文主题", "主题英文"} and len(parts) >= 2:
            topic_english = parts[1]
        elif len(parts) == len(fields) + 1 and parts[0].isdigit():
            rows.append(parts[1:])
    if not topic_english:
        raise InvalidVocabularyError("词表缺少“英文主题｜...”行")
    if len(rows) != WORDS_PER_TASK:
        raise InvalidVocabularyError(f"词表必须正好有 {WORDS_PER_TASK} 行，现在解析到 {len(rows)} 行")
    normalized, seen = [], set()
    for index, values in enumerate(rows, 1):
        item = dict(zip(fields, values))
        if any(not value for value in item.values()):
            raise InvalidVocabularyError(f"第 {index} 行存在空字段")
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
