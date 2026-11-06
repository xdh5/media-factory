"""宿主重点句定稿提示词与输入校验。"""

from __future__ import annotations

import json

_SYSTEM_PROMPT = "按内容价值挑选适合大字强调的核心观点、结论和建议，最多五句。选整句，略过过渡和普通叙述。"


def _build_prompt(rows: list[tuple[int, list[str]]]) -> str:
    listing = "\n".join(
        f"{index}. segments={json.dumps(lines, ensure_ascii=False)}" for index, lines in rows
    )
    return (
        "按编号选择整句，编号填 sentence。markers 填句首独占一段的纯引出语段数，没有填 0。\n"
        "lines 与其余内容段逐段对应，每段一至两行，每行约 14 个汉字。"
        "按语义断行，保留词语、数字、英文单词及标点，各行拼接须与原段逐字一致。\n"
        "line_keywords 与 lines 同形状，每行给 1～2 个来自该行的连续重点词。\n"
        '只输出 JSON，例如 {"groups":[{"sentence":2,"markers":1,'
        '"lines":[["第一行","第二行"],["短段"]],'
        '"line_keywords":[[["重点词1"],["重点词2"]],[["重点词3"]]]}]}。'
        '没有重点句时输出 {"groups":[]}。\n\n'
        f"{listing}"
    )


def validate_emphasis_groups(payload: dict, sentences: list[list[str]]) -> list[dict]:
    """程序校验：编号存在且不重复、markers 留有内容行、关键词在内容里；非法整组丢弃。"""
    groups: list[dict] = []
    used: set[int] = set()
    for raw in payload.get("groups") or []:
        if not isinstance(raw, dict):
            continue
        try:
            sentence = int(raw.get("sentence"))
        except (TypeError, ValueError):
            sentence_text = str(raw.get("sentence_text") or "")
            matches = [
                index for index, parts in enumerate(sentences)
                if "".join(parts) == sentence_text
            ]
            if len(matches) != 1:
                continue
            sentence = matches[0]
        if not 0 <= sentence < len(sentences) or sentence in used:
            continue
        try:
            markers = int(raw.get("markers") or 0)
        except (TypeError, ValueError):
            continue
        line_count = len(sentences[sentence])
        if markers < 0 or markers >= line_count:
            continue
        content_segments = sentences[sentence][markers:]
        display_lines: list[list[str]] = []
        line_keywords: list[list[list[str]]] = []
        raw_lines = raw.get("lines")
        raw_keywords = raw.get("line_keywords")
        if (
            isinstance(raw_lines, list)
            and isinstance(raw_keywords, list)
            and len(raw_lines) == len(content_segments)
            and len(raw_keywords) == len(content_segments)
        ):
            valid_lines = True
            for source, parts, keyword_parts in zip(content_segments, raw_lines, raw_keywords):
                if (
                    not isinstance(parts, list)
                    or not isinstance(keyword_parts, list)
                    or not 1 <= len(parts) <= 2
                    or len(parts) != len(keyword_parts)
                ):
                    valid_lines = False
                    break
                cleaned_parts = [str(part) for part in parts]
                if any(not part for part in cleaned_parts) or "".join(cleaned_parts) != source:
                    valid_lines = False
                    break
                cleaned_keywords: list[list[str]] = []
                for line, words in zip(cleaned_parts, keyword_parts):
                    if not isinstance(words, list):
                        valid_lines = False
                        break
                    valid_words = []
                    for word in words:
                        word = str(word or "").strip()
                        if word and word in line and word not in valid_words:
                            valid_words.append(word)
                    if not valid_words:
                        valid_lines = False
                        break
                    cleaned_keywords.append(valid_words[:2])
                if not valid_lines:
                    break
                display_lines.append(cleaned_parts)
                line_keywords.append(cleaned_keywords)
            if not valid_lines:
                display_lines = []
                line_keywords = []
        if not display_lines:
            continue
        used.add(sentence)
        groups.append({
            "sentence": sentence,
            "markers": markers,
            "lines": display_lines,
            "line_keywords": line_keywords,
        })
    return groups


__all__ = ["validate_emphasis_groups"]
