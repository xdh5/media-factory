"""MCP Prompt 模板读取。"""

from __future__ import annotations

from pathlib import Path

from .._constants import METADATA_PROMPT_PATH, SHOT_IMAGE_RULES_PATH
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


def build_storyboard_prompt(timeline: list[dict], *, radio: str, size: str) -> str:
    template = read_prompt(SHOT_IMAGE_RULES_PATH)
    table = "\n".join(f"{item['id']}|{item['duration']:.6f}|{item['text']}" for item in timeline)
    return render_template(template, radio=radio, size=size) + "\n\n" + table
