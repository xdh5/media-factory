"""宿主 Agent 与 GitHub Runner 共用的财经生成任务 Prompt、解析和校验。"""

from __future__ import annotations

import json
import re

from .._constants import ARTICLE_MAX_LINE_LENGTH, TOPIC_DEDUPLICATION_DAYS
from .._errors import WorkflowStepError
from .parse_metadata import parse_metadata
from .prompts import build_metadata_prompt
from .save_draft import _cover_highlights, _cover_lines

BRAND_NAME = "财富研习岛"
ARTICLE_LENGTH_RATIO_MIN = 0.80
ARTICLE_LENGTH_RATIO_MAX = 1.20


def _json_payload(response_text: str) -> dict:
    raw = str(response_text or "").strip().removeprefix("```json").removesuffix("```").strip()
    try:
        payload = json.loads(raw)
    except json.JSONDecodeError as exc:
        raise WorkflowStepError(f"模型输出不是有效 JSON：{exc}") from exc
    if not isinstance(payload, dict):
        raise WorkflowStepError("模型输出必须是 JSON 对象")
    return payload


def _bare(text: str) -> str:
    return re.sub(r"[\s\W_]+", "", str(text or ""))


def _pairs(value, *, default_target: str = "") -> list[tuple[str, str]]:
    rows = []
    for item in value if isinstance(value, list) else []:
        if not isinstance(item, dict):
            continue
        source = str(item.get("from") or "").strip()
        target = str(item.get("to") or "").strip() or default_target
        if source and target and source != target:
            rows.append((source, target))
    return rows


def _replace(text: str, rows: list[tuple[str, str]]) -> str:
    result = str(text or "")
    for source, target in rows:
        result = result.replace(source, target)
    return result


def build_source_hook_prompt(source_text: str, feedback: str = "") -> dict:
    source = str(source_text or "").strip()
    if not source:
        raise WorkflowStepError("source_text 不能为空")
    prompt = (
        "识别下面原稿开头完整的黄金钩子。黄金钩子必须从原稿第一个字开始连续复制，"
        "不得改字、改标点、补字或省略中间内容。只输出 JSON："
        "{\"source_hook\":\"原文开头钩子\"}。\n\n原稿：\n" + source
    )
    if feedback:
        prompt += f"\n\n上一次校验失败，必须修正：{feedback}"
    return {"system_prompt": "你是中文短视频审稿编辑，必须输出有效 JSON，不要输出 Markdown。", "user_prompt": prompt}


def validate_source_hook_response(source_text: str, response_text: str) -> dict:
    source = str(source_text or "").strip()
    hook = str(_json_payload(response_text).get("source_hook") or "")
    if not hook or not source.startswith(hook):
        raise WorkflowStepError("source_hook 必须从数据库原稿第一个字开始连续复制，且与原稿开头完全一致")
    return {"source_hook": hook}


def build_article_generation_prompt(article_prompt: str, source_text: str, source_hook: str, feedback: str = "", previous_response: str = "") -> dict:
    rule = (
        "\n\n只输出 JSON：{\"article\":\"断行后的完整正文\","
        f"\"replacements\":[{{\"from\":\"原品牌\",\"to\":\"{BRAND_NAME}\"}}],"
        "\"corrections\":[{\"from\":\"原稿错字\",\"to\":\"正确文字\"}]}。"
        "replacements 和 corrections 必须完整列出实际修改；措辞改写不用逐条报告。"
        f"每行不得超过 {ARTICLE_MAX_LINE_LENGTH} 字，正文长度须为原稿的 "
        f"{ARTICLE_LENGTH_RATIO_MIN}～{ARTICLE_LENGTH_RATIO_MAX} 倍。"
    )
    prompt = str(article_prompt or "").strip() + rule
    if feedback:
        prompt += (
            f"\n\n上一次校验失败：{feedback}\n请在上一版基础上定向修订。"
            f"\n原稿：\n{source_text}\n黄金钩子：\n{source_hook}\n上一版：\n{previous_response}"
        )
    return {
        "system_prompt": "你是中文短视频编辑，必须输出有效 JSON，不要输出 Markdown。",
        "user_prompt": prompt,
    }


def validate_article_response(source_text: str, source_hook: str, response_text: str) -> dict:
    payload = _json_payload(response_text)
    replacements = _pairs(payload.get("replacements"), default_target=BRAND_NAME)
    corrections = _pairs(payload.get("corrections"))
    mismatched = [row for row in replacements if _bare(row[1]) != _bare(BRAND_NAME)]
    if mismatched:
        raise WorkflowStepError(f"所有品牌只能替换为「{BRAND_NAME}」")
    processed_hook = _replace(_replace(source_hook, replacements), corrections)
    article = str(payload.get("article") or "").strip()
    if not _bare(article).startswith(_bare(processed_hook)):
        raise WorkflowStepError("正文必须以完成品牌替换和错字修正后的黄金钩子原样开头")
    long_lines = [(index, len(line.strip())) for index, line in enumerate(article.splitlines(), 1) if len(line.strip()) > ARTICLE_MAX_LINE_LENGTH]
    if long_lines:
        raise WorkflowStepError(f"正文存在超过 {ARTICLE_MAX_LINE_LENGTH} 字的行", {"long_lines": long_lines})
    source_size = len(_bare(source_text))
    ratio = len(_bare(article)) / source_size if source_size else 0
    if not ARTICLE_LENGTH_RATIO_MIN <= ratio <= ARTICLE_LENGTH_RATIO_MAX:
        raise WorkflowStepError(
            f"正文长度是原稿的 {ratio:.2f} 倍，必须在 {ARTICLE_LENGTH_RATIO_MIN}～{ARTICLE_LENGTH_RATIO_MAX} 之间"
        )
    return {"article": article, "source_hook": processed_hook, "replacements": payload.get("replacements") or [], "corrections": payload.get("corrections") or []}


def build_topic_prompt(article: str, recent_topics: list[str], requested_topic: str = "", feedback: str = "") -> dict:
    prompt = (
        "从下面正文提炼一个准确、简短的中文话题，不得改变正文主题。"
        f"用户提供的可选侧重点：{str(requested_topic or '').strip() or '无'}。"
        f"不得与最近 {TOPIC_DEDUPLICATION_DAYS} 天话题重复：{json.dumps(recent_topics, ensure_ascii=False)}。"
        f"\n\n正文：\n{article}"
    )
    if feedback:
        prompt += f"\n\n上一次校验失败：{feedback}"
    return {"system_prompt": "你是短视频选题编辑。只返回一个中文话题，不加序号、引号或说明。", "user_prompt": prompt}


def validate_topic_response(response_text: str, recent_topics: list[str]) -> dict:
    topic = str(response_text or "").strip().strip("“”\"'")
    if not topic:
        raise WorkflowStepError("话题不能为空")
    if topic.casefold() in {str(item).strip().casefold() for item in recent_topics}:
        raise WorkflowStepError(f"话题“{topic}”与最近话题重复")
    return {"topic": topic}


def build_metadata_generation_prompt(article: str, feedback: str = "") -> dict:
    base = build_metadata_prompt()["metadata_prompt"]
    prompt = (
        f"{base}\n\n正文：\n{article}\n\n"
        "只输出 JSON：{\"metadata\":\"长标题|短标题|标签一|标签二|标签三|标签四\","
        "\"cover_lines\":[\"封面第一行\"],\"cover_highlights\":[\"重点词\"],"
        "\"intro_scene\":\"人物身份 + 关键动作 + 环境细节\"}。"
    )
    if feedback:
        prompt += f"\n\n上一次校验失败：{feedback}"
    return {"system_prompt": "你是短视频标题编辑，必须输出有效 JSON，不要输出 Markdown。", "user_prompt": prompt}


def validate_metadata_response(response_text: str) -> dict:
    payload = _json_payload(response_text)
    metadata = parse_metadata(str(payload.get("metadata") or ""))
    lines = _cover_lines(payload.get("cover_lines"))
    highlights = _cover_highlights(metadata["title"], payload.get("cover_highlights"))
    intro_scene = str(payload.get("intro_scene") or "").strip()
    if not intro_scene:
        raise WorkflowStepError("stock_video 需要非空 intro_scene")
    return {**metadata, "cover_lines": lines, "cover_highlights": highlights, "intro_scene": intro_scene}

