"""财经 GitHub Action：读取宿主定稿，生成分镜素材并制作成片。"""

from __future__ import annotations

import json
from pathlib import Path


from ._mcp import MCPCallError, ProjectMCP
from ._shared import PROJECT_ROOT, qwen, json_text, write_summary


async def _storyboard(mcp, draft, config, attempts, context):
    feedback = ""
    for _ in range(attempts):
        text = qwen(
            str(context["storyboard_system_prompt"]),
            str(context["storyboard_prompt"]) + (f"\n\n上一次校验失败：{feedback}" if feedback else ""),
            max_tokens=12000,
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


async def _editorial(mcp, draft_path, storyboard, production_config, attempts):
    arguments = {"draft_path": draft_path, "storyboard_text": storyboard}
    inputs = await mcp.call("finance_prepare_editorial", {**arguments, "production_config": production_config})
    subtitle_input = json.dumps({
        "subtitle_texts": inputs["subtitle_texts"],
        "chapters": inputs["chapters"],
    }, ensure_ascii=False)
    feedback = ""
    for _ in range(attempts):
        try:
            emphasis = json_text(qwen(
                inputs["system_prompt"], inputs["emphasis_prompt"] + feedback,
                json_output=True,
            ))
            subtitles = json_text(qwen(
                "逐条把字幕译成简短口语英文，翻译对象的键逐字保留中文原文。按章节顺序拟标题，每条 1 至 6 字。"
                '只输出 JSON：{"translations":{"中文原文":"英文译文"},"titles":["章节标题"]}。',
                subtitle_input + feedback, json_output=True, max_tokens=16000,
            ))
            layout = {
                "emphasis_lines": {"groups": emphasis.get("groups")},
                "secondary_subtitles": {"translations": subtitles.get("translations")},
                "chapter_timeline": {"titles": subtitles.get("titles")},
            }
            finalized = production_config | {
                key: {**production_config.get(key, {}), **value} for key, value in layout.items()
            }
            await mcp.call("finance_validate_editorial", {**arguments, "production_config": finalized})
            return finalized
        except (ValueError, MCPCallError) as exc:
            feedback = f"\n上一次校验失败：{exc}"
    raise RuntimeError(f"财经定稿连续 {attempts} 次不合格：{feedback.strip()}")


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
        production_config = await _editorial(
            mcp, draft["draft_path"], storyboard, config["production_config"], int(retries["editorial"]),
        )
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
