"""重点句 AI 识别（按完整句子）。

字幕 cue 先由上层按句读边界归成完整句子，整句编号喂给千问，
让它判断哪些「完整句子」值得全屏大字强调。判定按内容价值把握，
不依赖关键词；选定即整句——句子里每个逗号段都必须一起上大字，
分多行堆叠，不允许只挑其中一段。
输出经程序校验，非法整组丢弃，千问不可用时静默跳过（本条视频不带大字层）。
"""

from __future__ import annotations

import hashlib
import json
import re
from pathlib import Path

from core.tools.qwen_text import QwenTextError, generate_text

from ._constants import DETECTION_CACHE_FILE_NAME

_PROMPT_VERSION = "v6-agent-layout-20260924"

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

_FENCE = re.compile(r"^```(?:json)?\s*|\s*```$")


def _parse_json(text: str) -> dict:
    cleaned = _FENCE.sub("", str(text or "").strip()).strip()
    try:
        payload = json.loads(cleaned)
    except json.JSONDecodeError as exc:
        raise ValueError(f"千问返回的不是有效 JSON：{exc}") from exc
    if not isinstance(payload, dict):
        raise ValueError("千问返回的 JSON 不是对象")
    return payload


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


def detect_emphasis_groups(
    sentences: list[list[str]],
    *,
    cache_path: str | Path | None = None,
    progress=None,
) -> list[dict]:
    """返回经校验的重点句组：[{"sentence": 行号, "markers": n, "keywords": [...]}]。

    sentences 每项是一个完整句子，按句内逗号段拆成的行文本列表。
    千问不可用或输出不合规时返回空列表，绝不抛错、绝不中断生产。
    """
    rows = [(index, lines) for index, lines in enumerate(sentences) if any(lines)]
    if len(rows) < 2:
        return []
    cache_file = Path(cache_path).resolve() if cache_path else None
    fingerprint = hashlib.sha256(
        (_PROMPT_VERSION + "|" + json.dumps(rows, ensure_ascii=False)).encode("utf-8")
    ).hexdigest()
    if cache_file is not None and cache_file.is_file():
        try:
            cached = json.loads(cache_file.read_text(encoding="utf-8"))
            if cached.get("fingerprint") == fingerprint:
                return list(cached.get("groups") or [])
        except (OSError, json.JSONDecodeError, ValueError):
            pass
    last_error = None
    for _ in range(2):
        try:
            result = generate_text(
                _SYSTEM_PROMPT,
                _build_prompt(rows),
                json_output=True,
                max_tokens=4000,
            )
            payload = _parse_json(result["text"])
            groups = validate_emphasis_groups(payload, sentences)
            if cache_file is not None:
                try:
                    cache_file.parent.mkdir(parents=True, exist_ok=True)
                    cache_file.write_text(
                        json.dumps({"fingerprint": fingerprint, "groups": groups}, ensure_ascii=False, indent=2),
                        encoding="utf-8",
                    )
                except OSError:
                    pass
            return groups
        except (QwenTextError, ValueError) as exc:
            last_error = exc
    if progress:
        progress(f"重点句识别失败，本条视频不带大字层：{last_error}")
    return []


__all__ = ["detect_emphasis_groups", "validate_emphasis_groups"]
