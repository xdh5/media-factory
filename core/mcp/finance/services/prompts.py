"""MCP Prompt 模板读取。"""

from __future__ import annotations

from pathlib import Path

from ..config.settings import (
    MATERIAL_AGENT_REFERENCE,
    MATERIAL_STOCK_VIDEO,
    STORYBOARD_PROMPT_PATH,
)
from ..errors import WorkflowStepError

_STORYBOARD_RULES = {
    MATERIAL_AGENT_REFERENCE: ("IMAGE", "图片描述", "镜头约 5 秒，每个画面都有人物。"),
    MATERIAL_STOCK_VIDEO: (
        "VIDEO",
        "英文视频检索词",
        "检索词简短，包含人物、地点和动作。素材覆盖配音时长，画面不循环。"
        "片头使用自己镜头的首帧和视频，后续镜头使用不同素材。",
    ),
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
    marker, field, rules = _STORYBOARD_RULES[material_strategy]
    template = read_prompt(STORYBOARD_PROMPT_PATH)
    table = "\n".join(f"{item['id']}|{item['duration']:.6f}|{item['text']}" for item in timeline)
    prompt = render_template(
        template, radio=radio, size=size, material_marker=marker, material_field=field, material_rules=rules,
    )
    return prompt + "\n\n" + table
