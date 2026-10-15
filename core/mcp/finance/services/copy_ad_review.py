"""判断财经口播是正常作品还是广告，并去掉正文中的插入广告。"""

from __future__ import annotations

import json
import re
from pathlib import Path

from core.tools.qwen_text import QwenTextError, generate_text

from ..errors import WorkflowStepError

_PROMPT_PATH = Path(__file__).resolve().parents[1] / "prompts" / "copy-ad-review.md"
_BARE_RE = re.compile(r"[\s\W_]+", re.UNICODE)


def _bare(text: str) -> str:
    return _BARE_RE.sub("", text)


def _keeps_original_order(cleaned: str, original: str) -> bool:
    """删广告后的字必须按原文顺序出现，防止模型改写留下的句子。"""
    cleaned_chars = _bare(cleaned)
    original_chars = _bare(original)
    if not cleaned_chars:
        return False
    index = 0
    for char in original_chars:
        if index < len(cleaned_chars) and cleaned_chars[index] == char:
            index += 1
    return index == len(cleaned_chars)


def _load_json(text: str) -> dict:
    payload = text.strip()
    if payload.startswith("```"):
        lines = payload.splitlines()
        if lines and lines[0].startswith("```"):
            lines = lines[1:]
        if lines and lines[-1].strip() == "```":
            lines = lines[:-1]
        payload = "\n".join(lines).strip()
    try:
        data = json.loads(payload)
    except json.JSONDecodeError as extra:
        raise WorkflowStepError("广告判断没有返回可解析的 JSON") from extra
    if not isinstance(data, dict):
        raise WorkflowStepError("广告判断结果必须是 JSON 对象")
    return data


def review_finance_transcript(transcript: str) -> dict:
    """返回 kind=normal 或 ad。正常作品的 text 已去掉中间插入的广告。"""
    original = str(transcript or "").strip()
    if not original:
        raise WorkflowStepError("待审稿的口播正文不能为空")
    system = _PROMPT_PATH.read_text(encoding="utf-8").strip()
    try:
        result = generate_text(
            system,
            f"口播正文：\n{original}",
            temperature=0,
            max_tokens=min(8192, max(1024, len(original) * 2)),
            json_output=True,
        )
    except QwenTextError as extra:
        raise WorkflowStepError(f"广告判断失败：{extra}") from extra
    if result.get("finish_reason") == "length":
        raise WorkflowStepError("广告判断被截断，请缩短该条口播后重试")
    data = _load_json(str(result.get("text") or ""))
    kind = str(data.get("kind") or "").strip().lower()
    if kind == "ad":
        return {"kind": "ad", "text": ""}
    if kind != "normal":
        raise WorkflowStepError("广告判断的 kind 只能是 normal 或 ad")
    cleaned = str(data.get("text") or "").strip()
    if not cleaned:
        return {"kind": "ad", "text": ""}
    if not _keeps_original_order(cleaned, original):
        raise WorkflowStepError("广告判断改写了正文，已停止使用该结果")
    return {"kind": "normal", "text": cleaned}
