"""MCP Prompt 模板读取。"""

from __future__ import annotations

from pathlib import Path

from .._constants import (
    ARTICLE_PROMPT_PATH,
    IMAGE_MATERIAL_STRATEGIES,
    MATERIAL_STRATEGIES,
    METADATA_PROMPT_PATH,
    SHOT_IMAGE_RULES_PATH,
    STOCK_VIDEO_RULES_PATH,
)
from .._errors import WorkflowStepError


def read_prompt(path: Path) -> str:
    if not path.is_file():
        raise WorkflowStepError(f"Prompt 不存在：{path}")
    return path.read_text(encoding="utf-8").strip()


def render_template(template: str, **values: object) -> str:
    result = template
    for key, value in values.items():
        result = result.replace("{{" + key + "}}", str(value))
    return result


def build_metadata_prompt() -> dict:
    return {"metadata_prompt": read_prompt(METADATA_PROMPT_PATH)}


def build_article_prompt(source_text: str, source_hook: str) -> dict:
    """返回已注入数据库原稿和黄金钩子的正文整理 Prompt。"""
    source = str(source_text or "").strip()
    hook = str(source_hook or "").strip()
    if not source:
        raise WorkflowStepError("source_text 不能为空")
    if not hook or not source.startswith(hook):
        raise WorkflowStepError("source_hook 必须是 source_text 开头的连续原文")
    return {
        "article_prompt": render_template(
            read_prompt(ARTICLE_PROMPT_PATH),
            source_text=source,
            source_hook=hook,
        )
    }


def rules_path_for_material(material_strategy: str) -> tuple[Path, str]:
    """按素材策略返回分镜规则文件与行标记（IMAGE / VIDEO）。"""
    strategy = str(material_strategy or "").strip()
    if strategy not in MATERIAL_STRATEGIES:
        raise WorkflowStepError(
            f"material_strategy 必须是 {'、'.join(MATERIAL_STRATEGIES)} 之一",
            {"material_strategy": strategy},
        )
    if strategy in IMAGE_MATERIAL_STRATEGIES:
        return SHOT_IMAGE_RULES_PATH, "IMAGE"
    return STOCK_VIDEO_RULES_PATH, "VIDEO"


def build_storyboard_prompt(
    timeline: list[dict],
    *,
    radio: str,
    size: str,
    material_strategy: str = MATERIAL_STRATEGIES[0],
) -> str:
    template_path, _ = rules_path_for_material(material_strategy)
    template = read_prompt(template_path)
    table = "\n".join(f"{item['id']}|{item['duration']:.6f}|{item['text']}" for item in timeline)
    return render_template(template, radio=radio, size=size) + "\n\n" + table
