"""宿主重点句定稿提示词与输入校验。"""

from __future__ import annotations

import json

_SYSTEM_PROMPT = (
    "你是中文短视频的排版导演，负责从字幕里挑出值得全屏大字强调的重点句。"
    "选取单位是完整句子：从句首到句号/问号/感叹号收束的整句，编号即整句。"
    "判定由你按内容价值把握，不依赖任何固定关键词：核心观点、结论、建议、"
    "分条要点、金句式断言、最值得观众记住的话都算重点句；"
    "普通的叙述、描写、故事推进、寒暄过渡不算。"
    "重点句可能以「第一/总之/所以」这类提示词开头，"
    "也可能以「真正清醒的活法是」这类引出语开头，也可能没有任何标志词。"
    "大字是稀缺资源，必须克制：只挑整条视频里分量最重的少数几句，"
    "宁缺毋滥，讲道理但平平的句子一律不选。"
)


def _build_prompt(rows: list[tuple[int, list[str]]]) -> str:
    listing = "\n".join(
        f"{index}. segments={json.dumps(lines, ensure_ascii=False)}" for index, lines in rows
    )
    return (
        "下面是按顺序编号的完整句子（来自同一支视频，每个编号就是一整句；"
        "segments 数组保留了句内各内容段边界）。\n"
        "按系统提示的标准挑出重点句：整条视频最多 5 句，宁缺毋滥。\n"
        "每选中一句输出一组：\n"
        "- sentence：句子编号；选中即整句，不允许只选句中的某一段。\n"
        "- markers：句首纯引出语的行数——句子开头只含提示词/引出语"
        "（如「第一，」「真正清醒的活法是，」）且单独占一个逗号段时，"
        "该段不上大字，只报它占几行；没有则为 0。\n"
        "- lines：内容段逐段对应的显示行数组，数量必须等于去掉 markers 后的内容段数。"
        "短段原样放一行；较长段按中文词语和语义拆成两行，尽量均衡，每行约 14 个汉字，"
        "禁止拆开一个词、固定搭配、数字或英文单词。lines 内所有文字按顺序拼接后必须与原段逐字一致，"
        "不得增删、替换或调整标点。\n"
        "- line_keywords：与 lines 完全同形状；每一显示行必须给 1~2 个需要标红的重点词，"
        "每个词必须是该行原文中的连续子串，禁止空数组。\n\n"
        "只输出 JSON：{\"groups\":[{\"sentence\":2,\"markers\":1,"
        "\"lines\":[[\"第一行\",\"第二行\"],[\"短段\"]],"
        "\"line_keywords\":[[[\"重点词1\"],[\"重点词2\"]],[[\"重点词3\"]]]}]}；"
        "确实没有任何重点句才输出 {\"groups\":[]}。\n\n"
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
