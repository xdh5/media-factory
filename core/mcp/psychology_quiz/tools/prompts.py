"""心灵鸡汤 Prompt 读取与分镜模板拼装。"""

from pathlib import Path

from .._constants import METADATA_PROMPT_PATH, STORYBOARD_PROMPT_PATH
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
    template = read_prompt(STORYBOARD_PROMPT_PATH)
    table = "\n".join(f"{item['id']}|{item['duration']:.6f}|{item['text']}" for item in timeline)
    return render_template(template, radio=radio, size=size) + "\n\n" + table
