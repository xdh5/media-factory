"""财经 GitHub Action：自动生成稿件并制作成片，不发布平台。"""

from __future__ import annotations

import json
import random
import re
from pathlib import Path

from core.tools.generate_image import choose_finance_library_line
from ._mcp import MCPCallError, ProjectMCP
from core.tools.cloudflare_data import commit_production_outputs
from ._shared import (
    PROJECT_ROOT,
    json_text,
    qwen,
    resolve_publish_date,
    upload_run_files,
    write_summary,
)


TTS_CONFIG = {"voice": "zh-CN-YunjianNeural", "rate": "+20%", "trim_trailing_silence": True}
PRODUCTION_CONFIG = {
    "cover_frame_seconds": 0.03333333333333333,
    "intro": "slide_in_shutter",
    "shot_stickers": ["rec"],
    "matrixmedia_account_group": "心灵鸡汤",
}
BGM_PATHS = (
    "core/tools/generate_bgm/static/nothing_to_fare.mp3",
    "core/tools/generate_bgm/static/aware.mp3",
)


def _article_prompt(source_text: str, source_hook: str) -> str:
    root = PROJECT_ROOT / ".agents" / "skills" / "finance"
    template = (root / "prompts" / "finance.md").read_text(encoding="utf-8")
    return template.replace("{{source_text}}", source_text).replace("{{source_hook}}", source_hook)


def _extract_source_hook(source_text: str) -> str:
    feedback = ""
    for _ in range(3):
        user_prompt = (
            "识别下面原稿开头完整的黄金钩子。黄金钩子必须从原稿第一个字开始连续复制，"
            "不得改字、改标点、补字或省略中间内容。只输出 {\"source_hook\":\"原文开头钩子\"}。\n\n"
            f"原稿：\n{source_text}"
        )
        if feedback:
            user_prompt += f"\n\n上一次输出校验失败，必须修正：{feedback}"
        result = qwen(
            "你是中文短视频审稿编辑，必须输出有效 JSON，不要输出 Markdown。",
            user_prompt,
            json_output=True,
            max_tokens=500,
        )
        hook = str(json_text(result).get("source_hook") or "")
        if hook and source_text.startswith(hook):
            return hook
        feedback = "source_hook 必须从原稿第一个字开始连续复制，且与原稿开头完全一致"
    raise ValueError("千问连续三次识别的黄金钩子都不是数据库原稿的精确开头")


def _article_length(article: str) -> int:
    return len(re.sub(r"\s+", "", article))


def _adapt_article(source_text: str, source_hook: str) -> str:
    prompt = _article_prompt(source_text, source_hook)
    last_error = None
    for _ in range(3):
        article = str(qwen("你是严谨的中文财经短视频改编编辑，只输出正文。", prompt, max_tokens=5000)["text"]).strip()
        length = _article_length(article)
        if article.startswith(source_hook) and 450 <= length <= 550:
            return article
        last_error = f"黄金钩子或字数不合格：当前 {length} 字"
        prompt += f"\n\n上一次结果不合格：{last_error}。请保持原结构重新调整。"
    raise RuntimeError(f"财经原稿连续三次改编不合格：{last_error}")


def _choose_topic(article: str, recent_topics: list[str], requested_topic: str) -> str:
    requested_hint = requested_topic.strip()
    recent_folded = {item.strip().casefold() for item in recent_topics}
    feedback = ""
    for _ in range(3):
        user_prompt = (
            "从下面已经改编好的正文提炼一个准确、简短的财经话题，不得改变正文主题。"
            f"用户提供的可选侧重点：{requested_hint or '无'}。"
            f"不得与最近30天话题重复：{json.dumps(recent_topics, ensure_ascii=False)}。\n\n正文：\n{article}"
        )
        if feedback:
            user_prompt += f"\n\n上一次输出校验失败，必须修正：{feedback}"
        result = qwen(
            "你是财经短视频选题编辑。只返回一个中文话题，不加序号、引号或说明。",
            user_prompt,
            max_tokens=100,
        )
        topic = str(result["text"]).strip().strip("“”\"'")
        if topic and topic.casefold() not in recent_folded:
            return topic
        if not topic:
            feedback = "话题不能为空"
        else:
            feedback = f"话题“{topic}”与最近30天话题重复，必须换一个"
    raise ValueError("千问连续三次生成的话题都为空或与最近30天话题重复")


def _metadata(metadata_prompt: str, article: str, *, feedback: str = "") -> dict:
    user_prompt = (
        f"{metadata_prompt}\n\n正文：\n{article}\n\n"
        "输出 JSON：{\"metadata\":\"长标题|短标题|标签一|标签二|标签三|标签四\","
        "\"cover_lines\":[\"封面第一行\",\"封面第二行\"],"
        "\"cover_highlights\":[\"重点词一\",\"重点词二\"]}。"
        "cover_lines 必须按语义拆成1至3行；"
        "cover_highlights 必须选择1至3个原样出现在长标题中的重点词。"
    )
    if feedback:
        user_prompt += f"\n\n上一次输出校验失败，必须修正：{feedback}"
    result = qwen(
        "你是财经短视频标题编辑，必须输出有效 JSON，不要输出 Markdown。",
        user_prompt,
        json_output=True,
        max_tokens=600,
    )
    payload = json_text(result)
    parts = [part.strip() for part in str(payload.get("metadata") or "").split("|")]
    if len(parts) != 6:
        raise ValueError("千问标题标签必须包含 6 个竖线字段")
    cover_lines = payload.get("cover_lines")
    if not isinstance(cover_lines, list):
        raise ValueError("千问标题结果缺少 cover_lines 数组")
    cover_highlights = payload.get("cover_highlights")
    if not isinstance(cover_highlights, list) or not cover_highlights:
        raise ValueError("千问标题结果缺少 cover_highlights 数组")
    return {
        "title": parts[0],
        "short_title": parts[1],
        "hashtags": parts[2:],
        "cover_lines": [str(item).strip() for item in cover_lines],
        "cover_highlights": [str(item).strip() for item in cover_highlights],
    }


def _select_images(prepared: dict) -> list[dict]:
    catalog = prepared.get("library_catalog") or []
    tasks = prepared.get("selection_tasks") or []
    compact_catalog = [{"id": row["id"], "caption": row["caption"]} for row in catalog]
    payload = json_text(qwen(
        "你是财经视频图库选图员。必须输出有效 JSON，不要输出 Markdown。",
        "为每个镜头选择语义最贴近的图库图片，同一图片允许重复使用。\n"
        f"镜头：{json.dumps(tasks, ensure_ascii=False)}\n"
        f"图库：{json.dumps(compact_catalog, ensure_ascii=False)}\n"
        "输出 {\"selections\":[{\"image_id\":\"shot-001\",\"library_id\":1}]}，覆盖全部镜头。",
        json_output=True,
        max_tokens=3000,
    ))
    by_id = {int(row["id"]): row for row in catalog}
    selected = payload.get("selections")
    if not isinstance(selected, list):
        raise ValueError("千问选图结果缺少 selections 数组")
    result = []
    for item in selected:
        row = by_id[int(item["library_id"])]
        result.append({"image_id": str(item["image_id"]), "image_path": row["image_path"]})
    if {item["image_id"] for item in result} != {item["image_id"] for item in tasks}:
        raise ValueError("千问选图结果没有完整覆盖全部镜头")
    return result


async def run(requested_topic: str = "", publish_date: str = "") -> dict:
    library_line = choose_finance_library_line()
    image_config = {"source": "local_library", "library_line": library_line}
    publish_date = resolve_publish_date(publish_date)
    async with ProjectMCP("core.mcp.finance", PROJECT_ROOT) as mcp:
        selected = await mcp.call("finance_get_source_script")
        source = selected["source"]
        reservation = selected["reservation"]
        source_text = str(source["transcript"]).strip()
        source_hook = _extract_source_hook(source_text)
        article = _adapt_article(source_text, source_hook)
        topics = await mcp.call("finance_get_topics")
        topic = _choose_topic(article, topics.get("recent_topics") or [], requested_topic)
        metadata_prompt = (await mcp.call("finance_get_metadata_prompt"))["metadata_prompt"]
        last_error = None
        for _ in range(3):
            try:
                metadata = _metadata(
                    metadata_prompt,
                    article,
                    feedback=str(last_error) if last_error else "",
                )
                draft = await mcp.call(
                    "finance_save_draft",
                    {
                        "topic": topic,
                        "article": article,
                        "source_aweme_id": str(source["aweme_id"]),
                        "source_reservation_token": str(reservation["reservation_token"]),
                        "source_hook": source_hook,
                        "publish_date": publish_date,
                        **metadata,
                    },
                )
                break
            except (ValueError, MCPCallError) as exc:
                last_error = exc
        else:
            raise RuntimeError(f"财经标题连续三次不合格：{last_error}")
        started = await mcp.call("finance_start_storyboard", {"draft_path": draft["draft_path"], "tts_config": TTS_CONFIG})
        storyboard_context = await mcp.poll("finance_poll_task", started["task_path"])
        storyboard_prompt = storyboard_context["storyboard_prompt"]
        last_error = None
        for _ in range(3):
            storyboard = qwen(
                "你是严格的视频分镜导演，只输出规定格式的 IMAGE 和 SUB 行。",
                storyboard_prompt,
                max_tokens=12000,
            )["text"]
            try:
                prepared = await mcp.call(
                    "finance_prepare_images",
                    {"draft_path": draft["draft_path"], "storyboard_text": storyboard, "image_config": image_config},
                )
                break
            except MCPCallError as exc:
                last_error = exc
                storyboard_prompt += f"\n\n上一次输出校验失败，必须修正：{exc}"
        else:
            raise RuntimeError(f"财经分镜连续三次不合格：{last_error}")
        selections = _select_images(prepared)
        image_manifest = await mcp.call(
            "finance_submit_images",
            {"context_path": prepared["context_path"], "images": selections},
        )
        production_config = {**PRODUCTION_CONFIG, "bgm_path": random.choice(BGM_PATHS)}
        started = await mcp.call(
            "finance_start_finish_video",
            {
                "draft_path": draft["draft_path"],
                "image_manifest_path": image_manifest["manifest_path"],
                "production_config": production_config,
                "storyboard_text": storyboard,
                "production_source": "github_workflow",
            },
        )
        manifest = await mcp.poll("finance_poll_task", started["task_path"])
    remote = upload_run_files(
        "finance",
        manifest["run_id"],
        [manifest["video_path"], manifest["cover_path"], manifest["title_path"], manifest["short_title_path"], manifest["publish_copy_path"]],
        manifest,
    )
    uploaded_by_name = {
        str(item.get("source_name") or ""): str(item.get("url") or "")
        for item in remote.get("files") or []
    }
    video_url = uploaded_by_name.get(Path(manifest["video_path"]).name, "")
    if not video_url:
        raise RuntimeError("财经成片已上传，但 R2 返回结果缺少视频地址")
    production_outputs = commit_production_outputs([{
        "production_id": f"github_workflow:finance:{manifest['run_id']}:finance:1",
        "run_id": manifest["run_id"],
        "publish_date": manifest["publish_date"],
        "business_line": "finance",
        "content_kind": "finance",
        "content_part": 1,
        "title": manifest["title"],
        "hashtags": " ".join(f"#{str(tag).lstrip('#')}" for tag in manifest.get("hashtags") or []),
        "source": "github_workflow",
        "local_path": None,
        "r2_url": video_url,
        "r2_expires_at": None,
    }])
    write_summary(
        "财经成片已生成",
        [
            ("话题", topic),
            ("标题", manifest["title"]),
            ("图库", library_line),
            ("BGM", production_config["bgm_path"].rsplit("/", 1)[-1]),
            ("R2 清单", remote["manifest"]["url"]),
            ("平台发布", "未执行"),
        ],
    )
    return {"manifest": manifest, "r2": remote, "production_outputs": production_outputs}
