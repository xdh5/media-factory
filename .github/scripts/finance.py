"""财经 GitHub Action：读取宿主定稿，生成分镜素材并制作成片。"""

from __future__ import annotations

import os


from tools.qwen_text import generate_text


async def _storyboard(context: dict) -> str:
    return generate_text(
        str(context["storyboard_system_prompt"]),
        str(context["storyboard_prompt"]),
        temperature=0.7, max_tokens=12000, model=os.getenv("DASHSCOPE_FINANCE_MODEL"),
    )["text"]


async def run(publish_date: str = "", content_part: int = 1) -> dict:
    from workflows.finance.production import run as produce
    return await produce(publish_date, content_part, storyboard_provider=_storyboard, production_source="github_workflow")
