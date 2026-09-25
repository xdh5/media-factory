"""重点句大字图层：AI 识别 + 居中堆叠 + 随机入场动画 + 普通字幕隐藏。

行为（2026-09-24 用户定稿）：
- 选取单位是完整句子：cue 按句读边界归成整句，由千问按内容价值挑选
  （不做关键词匹配）；选中即整句，句内每个逗号段都必须一起上大字；
- 每段大字最多两行（字魂群英体、白字黑边、重点词标红 #E30F13），
  句首纯引出语段（如「第一，」）不上大字；
- 同屏最多 5 行，放不下的后续内容恢复为普通字幕；
- 读到哪段、哪行带随机入场动画落在画面中央，逐行向下堆叠驻留；
- 大字驻留期间，普通 karaoke 字幕直接不展示（cue 打 hidden 标记）；
  本句读完大字整体消失、普通字幕恢复。
"""

from __future__ import annotations

import re
import unicodedata
from pathlib import Path

from ._ass import write_emphasis_ass
from ._constants import (
    DETECTION_CACHE_FILE_NAME,
    EMPHASIS_ANIMATION_DURATION,
    EMPHASIS_ANIMATIONS,
    EMPHASIS_BOLD,
    EMPHASIS_CENTER_RATIO,
    EMPHASIS_FONT_SIZE,
    EMPHASIS_HIGHLIGHT_COLOR,
    EMPHASIS_LINE_HEIGHT,
    EMPHASIS_MAX_LINE_WIDTH,
    EMPHASIS_MAX_VISIBLE_LINES,
    EMPHASIS_MAX_WRAPPED_LINES,
    EMPHASIS_OUTLINE,
    EMPHASIS_OUTLINE_COLOR,
    EMPHASIS_PRIMARY_COLOR,
)
from ._animations import SUPPORTED_ANIMATIONS
from ._detect import detect_emphasis_groups, validate_emphasis_groups

__all__ = ["generate_emphasis_lines", "DEFAULT_SETTINGS"]

DEFAULT_SETTINGS: dict = {
    "enabled": True,
    "font_size": EMPHASIS_FONT_SIZE,
    "primary_color": EMPHASIS_PRIMARY_COLOR,
    "highlight_color": EMPHASIS_HIGHLIGHT_COLOR,
    "outline_color": EMPHASIS_OUTLINE_COLOR,
    "outline": EMPHASIS_OUTLINE,
    "bold": EMPHASIS_BOLD,
    "center_ratio": EMPHASIS_CENTER_RATIO,
    "line_height": EMPHASIS_LINE_HEIGHT,
    "animations": list(EMPHASIS_ANIMATIONS),
    "animation_duration": EMPHASIS_ANIMATION_DURATION,
    "ai_detect": True,      # False 时本条视频不带大字层
    "seed": None,
    # 交互式 Finance 由宿主 Agent 传入；None 时仅供 GitHub Action 调用文本模型 API。
    "groups": None,
}

_TRAILING = re.compile(r"[，。！？、；：,.!?;:…]+$")
_EDGE_PUNCT = re.compile(r"^[，。！？、；：,.!?;:…]+|[，。！？、；：,.!?;:…]+$")
_BREAK_AFTER_PUNCT = set("，。！？、；：,.!?;:…")
_BREAK_BEFORE_WORDS = (
    "而且", "并且", "所以", "因此", "如果", "那么", "但是", "不过", "可是",
    "所谓", "其实", "真正", "必须", "才能", "全都", "已经", "仍然", "根本",
    "把", "被", "对", "从", "向", "给", "让", "换", "压",
)


def _clean_segment_text(text: str) -> str:
    """大字行去掉首尾标点（模型给的要点子串可能带句读）。"""
    return _EDGE_PUNCT.sub("", str(text or "").strip()).strip()


def _display_text(cue_text) -> str:
    if isinstance(cue_text, list):
        parts = []
        for span in cue_text:
            parts.append(span.get("text") if isinstance(span, dict) else str(span))
        raw = "".join(parts)
    else:
        raw = str(cue_text or "")
    cleaned = raw.replace("【", "").replace("】", "").strip()
    return _TRAILING.sub("", cleaned).rstrip()


def _logical_width(text: str) -> int:
    return sum(2 if unicodedata.east_asian_width(char) in {"W", "F"} else 1 for char in text)


def _inside_ascii_word(text: str, index: int) -> bool:
    left, right = text[index - 1], text[index]
    return left.isascii() and right.isascii() and left.isalnum() and right.isalnum()


def _wrap_emphasis_text(text: str, keywords: list[str] | None = None) -> list[str]:
    """超长重点字幕均衡拆成两行；英文/数字词内部绝不换行，中文优先语义边界。"""
    cleaned = " ".join(str(text or "").replace("\r", " ").replace("\n", " ").split())
    if _logical_width(cleaned) <= EMPHASIS_MAX_LINE_WIDTH:
        return [cleaned]
    protected = [str(word) for word in (keywords or []) if str(word)]

    def _breaks_keyword(index: int) -> bool:
        return any(
            start < index < start + len(word)
            for word in protected
            for start in [cleaned.find(word)]
            if start >= 0
        )

    natural_candidates = [
        index for index in range(1, len(cleaned))
        if not _inside_ascii_word(cleaned, index)
        and not _breaks_keyword(index)
    ]
    fitting_candidates = [
        index for index in natural_candidates
        if _logical_width(cleaned[:index].rstrip()) <= EMPHASIS_MAX_LINE_WIDTH
        and _logical_width(cleaned[index:].lstrip()) <= EMPHASIS_MAX_LINE_WIDTH
    ]
    candidates = fitting_candidates or natural_candidates
    if not candidates:
        return [cleaned]
    target = _logical_width(cleaned) / 2
    best = min(
        candidates,
        key=lambda index: (
            0 if (
                cleaned[index - 1] in _BREAK_AFTER_PUNCT
                or any(cleaned.startswith(word, index) for word in _BREAK_BEFORE_WORDS)
            ) else 1,
            abs(_logical_width(cleaned[:index]) - target),
        ),
    )
    lines = [cleaned[:best].rstrip(), cleaned[best:].lstrip()]
    return lines[:EMPHASIS_MAX_WRAPPED_LINES]


def _merge_settings(overrides: dict | None) -> dict:
    settings = dict(DEFAULT_SETTINGS)
    if overrides:
        unknown = set(overrides) - set(settings)
        if unknown:
            raise ValueError(f"emphasis_lines 含未知字段：{sorted(unknown)}")
        settings.update(overrides)
    animations = settings.get("animations")
    if not isinstance(animations, list) or not animations:
        raise ValueError("emphasis_lines.animations 必须是非空列表")
    invalid = [name for name in animations if name not in SUPPORTED_ANIMATIONS]
    if invalid:
        raise ValueError(f"emphasis_lines.animations 含不支持的动画：{invalid}")
    if not 0 < float(settings["center_ratio"]) < 1:
        raise ValueError("emphasis_lines.center_ratio 必须在 0 到 1 之间")
    if int(settings["font_size"]) < 24:
        raise ValueError("emphasis_lines.font_size 不能小于 24")
    return settings


def _build_sentences(
    candidates: list[tuple[int, str, bool | None]],
) -> tuple[list[list[str]], list[list[int]]]:
    """把候选 cue 归成完整句子。

    返回 (句子行文本列表, 每句对应的候选下标列表)。
    ends_sentence 标记来自分镜（TTS 原文不以逗号结尾即收句）；
    全部缺失时退化为每条 cue 自成一句（旧行为）。
    """
    if not any(flag is not None for _, _, flag in candidates):
        texts = [[text] for _, text, _ in candidates]
        positions = [[pos] for pos in range(len(candidates))]
        return texts, positions
    sentence_texts: list[list[str]] = []
    sentence_positions: list[list[int]] = []
    current_texts: list[str] = []
    current_positions: list[int] = []
    for pos, (_, text, flag) in enumerate(candidates):
        current_texts.append(text)
        current_positions.append(pos)
        if flag:
            sentence_texts.append(current_texts)
            sentence_positions.append(current_positions)
            current_texts = []
            current_positions = []
    if current_texts:
        sentence_texts.append(current_texts)
        sentence_positions.append(current_positions)
    return sentence_texts, sentence_positions


def generate_emphasis_lines(
    cues: list[dict],
    output_path: str | Path,
    width: int,
    height: int,
    settings: dict | None = None,
    *,
    cache_path: str | Path | None = None,
    progress=None,
) -> dict | None:
    """在 cues 上就地给内容句打 hidden 标记，并写出大字图层 ASS。

    返回 {"output_path", "groups", "repositioned"}；无重点句返回 None。
    """
    merged = _merge_settings(settings)
    if not merged.get("enabled", True):
        return None
    candidates: list[tuple[int, str, bool | None]] = []
    for index, cue in enumerate(cues):
        if not isinstance(cue, dict) or "position" in cue:
            continue
        if str(cue.get("language") or "zh") != "zh":
            continue
        text = _display_text(cue.get("text"))
        if text:
            flag = cue.get("ends_sentence")
            candidates.append((index, text, flag if isinstance(flag, bool) else None))
    if not candidates:
        return None
    sentences, sentence_positions = _build_sentences(candidates)

    explicit_groups = merged.get("groups")
    if explicit_groups is not None:
        if not isinstance(explicit_groups, list):
            raise ValueError("emphasis_lines.groups 必须是列表或 null")
        raw_groups = validate_emphasis_groups({"groups": explicit_groups}, sentences)
        if len(raw_groups) != len(explicit_groups):
            raise ValueError("emphasis_lines.groups 含无效重点句、断行或标红词；每行必须有原文重点词")
    elif merged.get("ai_detect", True):
        if cache_path is None:
            cache_path = Path(output_path).resolve().parent / DETECTION_CACHE_FILE_NAME
        raw_groups = detect_emphasis_groups(
            sentences,
            cache_path=cache_path,
            progress=progress,
        )
    else:
        raw_groups = []
    if not raw_groups:
        return None

    layout_groups: list[list[dict]] = []
    repositioned: list[int] = []
    for group in raw_groups:
        sentence_index = int(group["sentence"])
        markers = int(group["markers"])
        content_texts = sentences[sentence_index][markers:]
        cue_positions = sentence_positions[sentence_index][markers:]
        rows: list[dict] = []
        cue_indexes: list[int] = []
        for offset, pos in enumerate(cue_positions):
            cue_index = candidates[pos][0]
            cue = cues[cue_index]
            try:
                start = float(cue["start"])
                end = float(cue["end"])
            except (KeyError, TypeError, ValueError):
                rows = []
                break
            if end <= start:
                rows = []
                break
            cleaned_text = _clean_segment_text(content_texts[offset])
            llm_lines = group.get("lines") or []
            wrapped = (
                list(llm_lines[offset])
                if offset < len(llm_lines)
                else _wrap_emphasis_text(cleaned_text, list(group.get("keywords") or []))
            )
            if len(rows) + len(wrapped) > EMPHASIS_MAX_VISIBLE_LINES:
                break
            keyword_layout = group.get("line_keywords") or []
            wrapped_keywords = (
                list(keyword_layout[offset])
                if offset < len(keyword_layout)
                else [[] for _ in wrapped]
            )
            rows.extend(
                {
                    "text": line,
                    "keywords": list(wrapped_keywords[line_index]),
                    "start": start,
                }
                for line_index, line in enumerate(wrapped)
            )
            cue_indexes.append(cue_index)
        if not rows:
            continue
        group_end = max(float(cues[i]["end"]) for i in cue_indexes)
        for row in rows:
            row["group_end"] = group_end
        layout_groups.append(rows)
        repositioned.extend(cue_indexes)

    if not layout_groups:
        return None

    # 大字驻留期间普通字幕不展示：给内容句的 cue 打 hidden 标记，
    # generate_final_video 过滤字幕层（原「让位到底部」已废弃）。
    for index in repositioned:
        cues[index]["hidden"] = True

    destination = Path(output_path).resolve()
    destination.parent.mkdir(parents=True, exist_ok=True)
    write_emphasis_ass(destination, layout_groups, width, height, merged)
    return {
        "output_path": str(destination),
        "groups": layout_groups,
        "repositioned": repositioned,
    }
