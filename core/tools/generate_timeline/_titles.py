"""章节标题 AI 生成（千问）与兜底。

输入按时间顺序分好的各章正文片段，输出等长的短标题列表；
千问不可用或返回不合规时逐章兜底（取本章开头文字截断），保证生产不中断。
"""

from __future__ import annotations

import json
import re

from core.tools.qwen_text import QwenRequestError, generate_text

from ._constants import FALLBACK_TITLE_PREFIX, TITLE_MAX_CHARS
from ._errors import InvalidParameterError

_SYSTEM_PROMPT = (
    "你是财经短视频的章节编导。根据按顺序给出的各章节正文，为每一章起一个时间轴小标题。"
    f"要求：每章 {TITLE_MAX_CHARS} 个字以内（不含标点，2~4 字最佳）；"
    "直给、口语化、有信息量或悬念，像「引言」「利润陷阱」「买单逻辑」「流向追踪」「判断输出」"
    "「案例分享」「结语」这种风格；不要句号逗号等任何标点；各章标题不要重复。"
    '只输出 JSON 对象：{"titles": ["标题1", "标题2", ...]}，数量必须与章节数一致。'
)

_PUNCTUATION_PATTERN = re.compile(r"[，。！？；：、,.!?;:…\"'“”‘’（）()\[\]【】\s]")


def _fallback_title(index: int, text: str) -> str:
    cleaned = _PUNCTUATION_PATTERN.sub("", str(text or "")).strip()
    if len(cleaned) >= 2:
        return cleaned[:4]
    return f"{FALLBACK_TITLE_PREFIX}{index + 1}"


def _parse_titles(raw: str, count: int) -> list[str] | None:
    text = str(raw or "").strip()
    text = re.sub(r"^```(?:json)?\s*|\s*```$", "", text, flags=re.MULTILINE).strip()
    try:
        payload = json.loads(text)
    except json.JSONDecodeError:
        match = re.search(r"\{.*\}", text, flags=re.DOTALL)
        if not match:
            return None
        try:
            payload = json.loads(match.group(0))
        except json.JSONDecodeError:
            return None
    titles = payload.get("titles") if isinstance(payload, dict) else None
    if not isinstance(titles, list) or len(titles) != count:
        return None
    cleaned: list[str] = []
    for item in titles:
        title = _PUNCTUATION_PATTERN.sub("", str(item or "")).strip()
        if not title or len(title) > TITLE_MAX_CHARS + 2:
            return None
        cleaned.append(title[:TITLE_MAX_CHARS])
    if len(set(cleaned)) != len(cleaned):
        return None
    return cleaned


def fallback_chapter_titles(chapter_texts: list[str]) -> list[str]:
    """不调用千问的兜底标题：取本章开头文字截断。"""
    if not chapter_texts:
        raise InvalidParameterError("chapter_texts", "至少需要一个章节的正文片段")
    return [_fallback_title(index, text) for index, text in enumerate(chapter_texts)]


def generate_chapter_titles(
    chapter_texts: list[str],
    *,
    progress=None,
    temperature: float = 0.6,
) -> list[str]:
    """为每个章节生成短标题；失败时逐章兜底，绝不抛错中断生产。"""
    if not chapter_texts:
        raise InvalidParameterError("chapter_texts", "至少需要一个章节的正文片段")

    def note(message: str) -> None:
        if progress is not None:
            progress(message)

    user_prompt = "\n\n".join(
        f"第 {index + 1} 章正文：\n{str(text or '').strip()[:220]}"
        for index, text in enumerate(chapter_texts)
    )
    try:
        result = generate_text(
            _SYSTEM_PROMPT,
            user_prompt,
            temperature=temperature,
            max_tokens=160 + 40 * len(chapter_texts),
            json_output=True,
        )
    except Exception as exc:  # 千问任何异常都不中断生产
        note(f"章节标题 AI 生成失败，使用兜底标题：{type(exc).__name__}")
        if not isinstance(exc, (QwenRequestError,)):
            note(f"章节标题生成异常详情：{exc}")
        return [_fallback_title(index, text) for index, text in enumerate(chapter_texts)]

    titles = _parse_titles(result.get("text"), len(chapter_texts))
    if titles is None:
        note("章节标题 AI 返回不合规，使用兜底标题")
        return [_fallback_title(index, text) for index, text in enumerate(chapter_texts)]
    note(f"章节标题 AI 生成完成：{'、'.join(titles)}")
    return titles
