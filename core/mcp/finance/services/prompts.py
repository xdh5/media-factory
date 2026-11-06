"""MCP Prompt 模板读取。"""

from __future__ import annotations

from pathlib import Path

from ..config.settings import (
    MATERIAL_AGENT_REFERENCE,
    MATERIAL_STOCK_VIDEO,
    SHOT_IMAGE_RULES_PATH,
    STOCK_VIDEO_RULES_PATH,
)
from ..errors import WorkflowStepError

_STORYBOARD_RULES = {
    MATERIAL_AGENT_REFERENCE: SHOT_IMAGE_RULES_PATH,
    MATERIAL_STOCK_VIDEO: STOCK_VIDEO_RULES_PATH,
}


def read_prompt(path: Path) -> str:
    if not path.is_file():
        raise WorkflowStepError(f"Prompt 不存在：{path}")
    return path.read_text(encoding="utf-8").strip()


def render_template(template: str, **values: object) -> str:
    result = template
    for key, value in values.items():
        result = result.replace("{{" + key + "}}", str(value))
    return result


def build_storyboard_prompt(
    timeline: list[dict],
    *,
    radio: str,
    size: str,
    material_strategy: str,
) -> str:
    template_path = _STORYBOARD_RULES[material_strategy]
    template = read_prompt(template_path)
    table = "\n".join(f"{item['id']}|{item['duration']:.6f}|{item['text']}" for item in timeline)
    return render_template(template, radio=radio, size=size) + "\n\n" + table
