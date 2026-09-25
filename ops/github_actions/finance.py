"""财经 GitHub Action：仅由千问执行模型调用，其余逻辑以 Finance MCP 为准。"""

from __future__ import annotations

import hashlib
import json
from pathlib import Path

from core.tools.generate_image import generate_qwen_image

from ._mcp import MCPCallError, ProjectMCP
from ._shared import PROJECT_ROOT, qwen, write_summary


async def _generate_checked(mcp, prompt_tool, validate_tool, prompt_args, validate_args, *, attempts=3, max_tokens=1000, json_output=False):
    feedback = ""
    for _ in range(attempts):
        prompt = await mcp.call(prompt_tool, {**prompt_args, "feedback": feedback})
        response = qwen(prompt["system_prompt"], prompt["user_prompt"], json_output=json_output, max_tokens=max_tokens)["text"]
        try:
            return await mcp.call(validate_tool, {**validate_args, "response_text": response}), response
        except MCPCallError as exc:
            feedback = str(exc)
    raise RuntimeError(f"{validate_tool} 连续 {attempts} 次校验失败：{feedback}")


async def _source_hook(mcp, source_text, attempts):
    result, _ = await _generate_checked(
        mcp, "finance_get_source_hook_prompt", "finance_validate_source_hook_response",
        {"source_text": source_text}, {"source_text": source_text},
        attempts=attempts, max_tokens=500, json_output=True,
    )
    return str(result["source_hook"])


async def _article(mcp, source_text, source_hook, attempts):
    plan = await mcp.call("finance_get_article_chunk_plan", {
        "source_text": source_text, "source_hook": source_hook,
    })
    articles, replacements, corrections = [], [], []
    for chunk in plan["chunks"]:
        feedback, previous = "", ""
        chunk_index = int(chunk["index"])
        chunk_text = str(chunk["source_text"])
        chunk_hook = source_hook if bool(chunk["is_hook"]) else ""
        for _ in range(attempts):
            prompt = await mcp.call("finance_get_article_chunk_generation_prompt", {
                "source_chunk": chunk_text,
                "source_hook": chunk_hook,
                "feedback": feedback,
                "previous_response": previous,
            })
            previous = qwen(prompt["system_prompt"], prompt["user_prompt"], json_output=True, max_tokens=3000)["text"]
            try:
                result = await mcp.call("finance_validate_article_chunk_response", {
                    "source_chunk": chunk_text,
                    "source_hook": chunk_hook,
                    "response_text": previous,
                })
                articles.append(str(result["article"]))
                replacements.extend(result.get("replacements") or [])
                corrections.extend(result.get("corrections") or [])
                break
            except MCPCallError as exc:
                feedback = str(exc)
        else:
            raise RuntimeError(f"财经正文第 {chunk_index} 段连续 {attempts} 次不合格：{feedback}")
    response = json.dumps({
        "article": "\n".join(articles),
        "replacements": replacements,
        "corrections": corrections,
    }, ensure_ascii=False)
    result = await mcp.call("finance_validate_article_response", {
        "source_text": source_text, "source_hook": source_hook, "response_text": response,
    })
    return str(result["article"]), str(result["source_hook"])


async def _topic(mcp, article, recent_topics, requested_topic, attempts):
    result, _ = await _generate_checked(
        mcp, "finance_get_topic_generation_prompt", "finance_validate_topic_response",
        {"article": article, "recent_topics": recent_topics, "requested_topic": requested_topic},
        {"recent_topics": recent_topics}, attempts=attempts, max_tokens=100,
    )
    return str(result["topic"])


async def _metadata(mcp, article, attempts):
    result, _ = await _generate_checked(
        mcp, "finance_get_metadata_generation_prompt", "finance_validate_metadata_response",
        {"article": article}, {}, attempts=attempts, max_tokens=800, json_output=True,
    )
    return result


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


async def _video_selections(mcp, context_path, attempts):
    result, _ = await _generate_checked(
        mcp, "finance_get_stock_video_selection_prompt", "finance_validate_stock_video_selection_response",
        {"context_path": context_path}, {"context_path": context_path},
        attempts=attempts, max_tokens=5000, json_output=True,
    )
    return list(result["selections"])


def _intro_image(prompt, size, draft):
    destination = Path(str(draft["cache_dir"])).resolve() / "stock-videos" / "intro-image.png"
    signature = hashlib.sha256(str(prompt).encode("utf-8")).hexdigest()
    return str(generate_qwen_image(str(prompt), destination, size=str(size), cache_signature=signature)["output_path"])


async def run(
    requested_topic: str = "",
    publish_date: str = "",
    content_part: int = 1,
    additional_recent_topics: list[str] | None = None,
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
        source_text = str(source["transcript"]).strip()
        hook = await _source_hook(mcp, source_text, int(retries["source_hook"]))
        article, processed_hook = await _article(mcp, source_text, hook, int(retries["article"]))
        topics = await mcp.call("finance_get_topics")
        recent_topics = list(topics.get("recent_topics") or [])
        for recent_topic in additional_recent_topics or []:
            normalized_topic = str(recent_topic or "").strip()
            if normalized_topic and normalized_topic not in recent_topics:
                recent_topics.append(normalized_topic)
        topic = await _topic(mcp, article, recent_topics, requested_topic, int(retries["topic"]))
        metadata = await _metadata(mcp, article, int(retries["metadata"]))
        draft = await mcp.call("finance_save_draft", {
            "topic": topic, "article": article, "source_aweme_id": str(source["aweme_id"]),
            "source_reservation_token": str(reservation["reservation_token"]),
            "source_hook": processed_hook, "publish_date": publish_date,
            "content_part": content_part, **metadata,
        })

        storyboard, prepared = await _storyboard(mcp, draft, config, int(retries["storyboard"]))
        selections = await _video_selections(mcp, str(prepared["context_path"]), int(retries["stock_video_selection"]))
        started = await mcp.call("finance_start_download_videos", {
            "context_path": prepared["context_path"], "selections": selections,
        })
        materials = await mcp.poll("finance_poll_task", started["task_path"])
        intro_path = _intro_image(prepared["intro_image_prompt"], prepared["intro_image_size"], draft)
        started = await mcp.call("finance_start_finish_video", {
            "draft_path": draft["draft_path"], "material_manifest_path": materials["manifest_path"],
            "intro_image_path": intro_path, "production_config": config["production_config"],
            "storyboard_text": storyboard, "production_source": "github_workflow",
        })
        manifest = await mcp.poll("finance_poll_task", started["task_path"])
        started = await mcp.call("finance_start_upload_r2", {
            "manifest_path": manifest["manifest_path"], "run_id": manifest["run_id"],
        })
        remote = await mcp.poll("finance_poll_task", started["task_path"])

    write_summary("财经成片已生成", [
        ("内容分片", str(content_part)), ("话题", topic), ("标题", manifest["title"]),
        ("素材策略", str(config["material_strategy"])),
        ("视频来源", ", ".join(config["video_config"]["providers"])),
        ("BGM", Path(config["production_config"]["bgm_path"]).name),
        ("R2 清单", remote["manifest_url"]), ("平台发布", "未执行"),
    ])
    return {"manifest": manifest, "r2": remote, "production_outputs": remote["production_outputs"]}
