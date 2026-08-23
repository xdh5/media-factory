"""财经 GitHub Action：自动生成稿件并制作成片，不发布平台。"""

from __future__ import annotations

import json

from ._mcp import MCPCallError, ProjectMCP
from ._shared import PROJECT_ROOT, json_text, qwen, restore_finance_library, upload_run_files, write_summary


TTS_CONFIG = {"voice": "zh-CN-YunjianNeural", "rate": "+20%", "trim_trailing_silence": True}
IMAGE_CONFIG = {"source": "local_library", "library_line": "finance"}
PRODUCTION_CONFIG = {
    "bgm_path": "core/tools/generate_bgm/static/cinematic-inspirational-piano-ambient-128209.mp3",
    "cover_frame_seconds": 0.03333333333333333,
    "intro": "slide_in_shutter",
    "shot_stickers": ["rec"],
    "matrixmedia_account_group": "心灵鸡汤",
}


def _article_prompt(topic: str) -> str:
    root = PROJECT_ROOT / ".agents" / "skills" / "finance"
    template = (root / "prompts" / "finance.md").read_text(encoding="utf-8")
    hooks = (root / "examples" / "hooks.txt").read_text(encoding="utf-8").strip()
    examples = []
    for path in sorted((root / "examples").glob("*.txt")):
        if path.name == "hooks.txt":
            continue
        examples.append(f"### {path.name}\n{path.read_text(encoding='utf-8').strip()}")
    return template.replace("{{topic}}", topic).replace("{{hooks}}", hooks).replace(
        "{{article_examples}}", "\n\n".join(examples)
    )


def _choose_topic(recent_topics: list[str], requested_topic: str) -> str:
    if requested_topic.strip():
        return requested_topic.strip()
    result = qwen(
        "你是财经短视频选题编辑。只返回一个中文话题，不加序号、引号或说明。",
        "选择一个长期有效、适合普通人的理财常识、经济现象或风险提醒。"
        f"不得与最近30天话题重复：{json.dumps(recent_topics, ensure_ascii=False)}",
        max_tokens=100,
    )
    return str(result["text"]).strip().strip("“”\"'")


def _metadata(metadata_prompt: str, article: str) -> dict:
    result = qwen(
        "你是财经短视频标题编辑，必须输出有效 JSON，不要输出 Markdown。",
        f"{metadata_prompt}\n\n正文：\n{article}\n\n"
        "输出 JSON：{\"metadata\":\"长标题|短标题|标签一|标签二|标签三|标签四\","
        "\"cover_lines\":[\"封面第一行\",\"封面第二行\"]}。"
        "cover_lines 必须按语义拆成1至3行，去掉空白拼接后与长标题完全相同。",
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
    return {
        "title": parts[0],
        "short_title": parts[1],
        "hashtags": parts[2:],
        "cover_lines": [str(item).strip() for item in cover_lines],
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


async def run(requested_topic: str = "") -> dict:
    restore_finance_library()
    async with ProjectMCP("core.mcp.finance", PROJECT_ROOT) as mcp:
        topics = await mcp.call("finance_get_topics")
        topic = _choose_topic(topics.get("recent_topics") or [], requested_topic)
        article = qwen(
            "你是严谨的中文财经短视频作者，只输出正文。",
            _article_prompt(topic),
            max_tokens=5000,
        )["text"]
        metadata_prompt = (await mcp.call("finance_get_metadata_prompt"))["metadata_prompt"]
        last_error = None
        for _ in range(3):
            try:
                metadata = _metadata(metadata_prompt, article)
                draft = await mcp.call("finance_save_draft", {"topic": topic, "article": article, **metadata})
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
                    {"draft_path": draft["draft_path"], "storyboard_text": storyboard, "image_config": IMAGE_CONFIG},
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
        started = await mcp.call(
            "finance_start_finish_video",
            {
                "draft_path": draft["draft_path"],
                "image_manifest_path": image_manifest["manifest_path"],
                "production_config": PRODUCTION_CONFIG,
                "storyboard_text": storyboard,
            },
        )
        manifest = await mcp.poll("finance_poll_task", started["task_path"])
    remote = upload_run_files(
        "finance",
        manifest["run_id"],
        [manifest["video_path"], manifest["cover_path"], manifest["title_path"], manifest["short_title_path"], manifest["publish_copy_path"]],
        manifest,
    )
    write_summary(
        "财经成片已生成",
        [("话题", topic), ("标题", manifest["title"]), ("R2 清单", remote["manifest"]["url"]), ("平台发布", "未执行")],
    )
    return {"manifest": manifest, "r2": remote}
