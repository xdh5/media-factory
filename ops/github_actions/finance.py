"""财经 GitHub Action：读取宿主定稿，生成分镜素材并制作成片。"""

from __future__ import annotations

import json
from pathlib import Path


from ._mcp import MCPCallError, ProjectMCP
from ._shared import PROJECT_ROOT, qwen, json_text, write_summary


async def _storyboard(mcp, draft, config, attempts):
    started = await mcp.call("finance_start_storyboard", {
        "draft_path": draft["draft_path"], "tts_config": config["tts_config"],
        "material_strategy": config["material_strategy"],
    })
    context = await mcp.poll("finance_poll_task", started["task_path"])
    feedback = ""
    for _ in range(attempts):
        text = qwen(
            str(context["storyboard_system_prompt"]),
            str(context["storyboard_prompt"]) + (f"\n\n上一次校验失败：{feedback}" if feedback else ""),
            max_tokens=12000,
        )["text"]
        try:
            started = await mcp.call("finance_start_video_search", {
                "draft_path": draft["draft_path"], "storyboard_text": text,
                "video_config": config["video_config"],
            })
            return text, await mcp.poll("finance_poll_task", started["task_path"])
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
        config = await mcp.call("finance_get_production_config")
        retries = config["runner_retry_config"]
        if str(config["material_strategy"]) != "stock_video":
            raise RuntimeError("Finance MCP 默认素材策略必须是 stock_video")

        selected = await mcp.call("finance_get_source_script")
        source, reservation = selected["source"], selected["reservation"]
        editorial = source["editorial"]
        topic = editorial["topic"]
        print(f"财经定稿：来源={source['aweme_id']} 标题={editorial['title']} 话题={topic}", flush=True)
        draft = await mcp.call("finance_save_draft", {
            **{key: editorial[key] for key in ("topic", "article", "title", "short_title", "hashtags", "cover_lines", "cover_highlights", "source_hook", "db_source_hook")},
            "source_aweme_id": str(source["aweme_id"]),
            "source_reservation_token": str(reservation["reservation_token"]),
            "publish_date": publish_date, "content_part": content_part,
        })

        storyboard, prepared = await _storyboard(mcp, draft, config, int(retries["storyboard"]))
        editorial_input = await mcp.call("finance_get_video_editorial_input", {
            "draft_path": draft["draft_path"], "storyboard_text": storyboard,
            "production_config": config["production_config"],
        })
        layout = json_text(qwen(
            editorial_input["system_prompt"],
            json.dumps(editorial_input, ensure_ascii=False) +
            '\n只输出 JSON：{"emphasis_lines":{"groups":[]},"secondary_subtitles":{"translations":{"中文原文":"英文译文"}},"chapter_timeline":{"titles":["章节标题"]}}。按输入真实定稿，不得省略字段。',
            json_output=True, max_tokens=16000,
        ))
        for key in ("emphasis_lines", "secondary_subtitles", "chapter_timeline"):
            config["production_config"][key] = {**config["production_config"].get(key, {}), **layout[key]}
        started = await mcp.call("finance_start_download_videos", {
            "context_path": prepared["context_path"],
            "production_config": config["production_config"],
            "production_source": "github_workflow",
        })
        manifest = await mcp.poll("finance_poll_task", started["task_path"])
        uploaded = await mcp.call("finance_start_upload_r2", {
            "manifest_path": str(manifest["manifest_path"]),
            "run_id": str(manifest["run_id"]),
        })
        remote = await mcp.poll("finance_poll_task", uploaded["task_path"])

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
