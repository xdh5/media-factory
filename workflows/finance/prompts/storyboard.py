"""将本期配音台词附加到财经分镜提示词。"""

from workflows.finance.parameters import STORYBOARD_PROMPT_PATH


def build_storyboard_prompt(timeline: list[dict], *, radio: str, size: str) -> str:
    template = STORYBOARD_PROMPT_PATH.read_text(encoding="utf-8").strip()
    template = template.replace("{{radio}}", radio).replace("{{size}}", size)
    table = "\n".join(f"{item['id']}|{item['duration']:.6f}|{item['text']}" for item in timeline)
    return template + "\n\n" + table
