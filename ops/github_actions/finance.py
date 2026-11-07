"""财经 GitHub Action：读取宿主定稿，生成分镜素材并制作成片。"""

from __future__ import annotations

import os
from pathlib import Path


from ._mcp import MCPCallError, ProjectMCP
from ._shared import PROJECT_ROOT, qwen, write_summary


async def _storyboard(mcp, draft, config, attempts, context):
    feedback = ""
    for _ in range(attempts):
        text = qwen(
            str(context["storyboard_system_prompt"]),
            str(context["storyboard_prompt"]) + (f"\n\n上一次校验失败：{feedback}" if feedback else ""),
            max_tokens=12000,
            model=os.getenv("DASHSCOPE_FINANCE_MODEL"),
        )["text"]
        try:
            started = await mcp.call("finance_prepare_visuals", {
                "draft_path": draft["draft_path"], "storyboard_text": text,
                "material_strategy": config["material_strategy"],
            })
            return text, await mcp.poll("finance_get_task", started["task_path"])
        except MCPCallError as exc:
            feedback = str(exc)
    raise RuntimeError(f"财经分镜连续 {attempts} 次不合格：{feedback}")


async def run(
    publish_date: str = "",
    content_part: int = 1,
) -> dict:
    if not str(publish_date or "").strip():
        raise ValueError("GitHub 财经生产必须明确传入 publish_date")
    async with ProjectMCP("core.mcp.finance", PROJECT_ROOT) as mcp:
        config = await mcp.call("finance_get_config")
        retries = config["runner_retry_config"]
        if str(config["material_strategy"]) != "stock_video":
            raise RuntimeError("Finance MCP 默认素材策略必须是 stock_video")

        started = await mcp.call("finance_start_production", {
            "publish_date": publish_date, "content_part": content_part,
        })
        context = await mcp.poll("finance_get_task", started["task_path"])
        draft = context["draft"]
        topic = context["source"]["editorial"]["topic"]
        storyboard, prepared = await _storyboard(mcp, draft, config, int(retries["storyboard"]), context)
        production_config = config["production_config"] | {
            "emphasis_lines": {"enabled": False},
            "secondary_subtitles": {"enabled": False},
            "chapter_timeline": {"enabled": False},
        }
        started = await mcp.call("finance_submit_visuals", {
            "context_path": prepared["context_path"], "material_strategy": "stock_video",
        })
        materials = await mcp.poll("finance_get_task", started["task_path"])
        started = await mcp.call("finance_start_render", {
            "draft_path": draft["draft_path"], "storyboard_text": storyboard,
            "material_manifest_path": materials["manifest_path"],
            "production_config": production_config,
            "production_source": "github_workflow", "upload_r2": True,
        })
        manifest = await mcp.poll("finance_get_task", started["task_path"])
        remote = manifest["r2"]

    write_summary("财经成片已生成", [
        ("内容分片", str(content_part)), ("话题", topic), ("标题", manifest["title"]),
        ("素材策略", str(config["material_strategy"])),
        ("视频来源", ", ".join(config["video_config"]["providers"])),
        ("BGM", Path(config["production_config"]["bgm_path"]).name),
        ("本地成片", manifest["video_path"]),
        ("R2", str(remote["video_url"])),
    ])
    return {
        "manifest": manifest,
        "r2": remote,
        "production_outputs": remote["production_outputs"],
    }
