"""双语字幕的英文翻译：千问批量翻译，失败兜底不中断生产。"""

from __future__ import annotations

import json
import re

from core.tools.qwen_text import generate_text

__all__ = ["translate_cue_texts"]

_CHUNK_SIZE = 20

_SYSTEM_PROMPT = (
    "你是财经短视频的字幕翻译。把按顺序给出的中文字幕逐条翻译成地道、简短的英文口语。"
    "要求：一条对应一条，顺序不变；不添不减，不输出引号或编号；"
    "每条尽量不超过 60 个英文字符，语气口语化。"
    '只输出 JSON 对象：{"translations": ["translation 1", "translation 2", ...]}，'
    "数量必须与输入条数一致。"
)


def _parse_translations(raw: str, count: int) -> list[str] | None:
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
    items = payload.get("translations") if isinstance(payload, dict) else None
    if not isinstance(items, list) or len(items) != count:
        return None
    cleaned = [re.sub(r"\s+", " ", str(item or "")).strip() for item in items]
    if any(not item for item in cleaned):
        return None
    return cleaned


def translate_cue_texts(
    texts: list[str],
    *,
    progress=None,
    temperature: float = 0.3,
) -> list[str | None]:
    """逐条把中文字幕翻译成英文；失败的位置返回 None，绝不抛错中断生产。"""
    results: list[str | None] = [None] * len(texts)

    def note(message: str) -> None:
        if progress is not None:
            progress(message)

    unique: dict[str, None] = {}
    for text in texts:
        unique.setdefault(text, None)
    pool = list(unique)
    if not pool:
        return results

    translated: dict[str, str] = {}
    for start in range(0, len(pool), _CHUNK_SIZE):
        chunk = pool[start : start + _CHUNK_SIZE]
        user_prompt = "\n".join(
            f"{index + 1}. {text}" for index, text in enumerate(chunk)
        )
        try:
            result = generate_text(
                _SYSTEM_PROMPT,
                user_prompt,
                temperature=temperature,
                max_tokens=120 + 80 * len(chunk),
                json_output=True,
            )
        except Exception as exc:
            note(f"英文字幕翻译失败（{type(exc).__name__}），跳过本批 {len(chunk)} 条")
            continue
        parsed = _parse_translations(result.get("text"), len(chunk))
        if parsed is None:
            note("英文字幕翻译返回不合规，跳过本批")
            continue
        for source, target in zip(chunk, parsed):
            translated[source] = target
    note(f"英文字幕翻译完成 {len(translated)}/{len(pool)} 条")
    for index, text in enumerate(texts):
        results[index] = translated.get(text)
    return results
