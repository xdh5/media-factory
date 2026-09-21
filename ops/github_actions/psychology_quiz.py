"""心理测试 GitHub Action：千问代替宿主 Agent 完成写稿、分镜和选图。"""

from __future__ import annotations

import json
import hashlib
import random
from pathlib import Path

from core.tools.cloudflare_data import commit_production_outputs
from core.tools.generate_image import generate_qwen_image
from ._mcp import MCPCallError, ProjectMCP
from ._shared import PROJECT_ROOT, json_text, qwen, resolve_publish_date, upload_run_files, write_summary

TTS_CONFIG = {"voice": "zh-CN-YunjianNeural", "rate": "+20%", "trim_trailing_silence": True}
PRODUCTION_CONFIG = {
    "cover_frame_seconds": 0.03333333333333333,
    "intro": "slide_in_shutter",
    "shot_stickers": ["rec"],
    "matrixmedia_account_group": "心灵鸡汤",
    "subtitle_style": {
        "font_size": 92,
        "primary_color": "#FFFFFF",
        "outline_color": "#000000",
        "outline": 5,
        "bold": True,
        "max_lines": 2,
    },
    "subtitle_position": {"alignment": 5, "margin_vertical_ratio": 0.5},
    "quiz_timeline_position": "bottom",
    "quiz_chapter_titles": [
        "情境引入",
        "A/B/C/D怎么选",
        "选好了吗",
        "四种答案解析",
        "评论区见",
    ],
}
BGM_PATHS = (
    "core/tools/generate_bgm/static/nothing_to_fare.mp3",
    "core/tools/generate_bgm/static/aware.mp3",
)


def _generate_quiz(prompt: str, recent_topics: list[str], requested_topic: str, feedback: str = "") -> dict:
    user_prompt = (
        f"{prompt}\n\n"
        f"最近30天已用主题：{json.dumps(recent_topics, ensure_ascii=False)}\n"
        f"用户可选侧重点：{requested_topic.strip() or '无'}\n"
        "生成一条全新的生活化心理测试，不得使用最近主题的同义改写。"
        "输出 JSON：topic、quiz、article、title、short_title、hashtags、cover_lines、cover_highlights。"
        "quiz 包含 category、scene_title、scenario、options、results、video_keywords；"
        "options 和 results 都使用 a、b、c、d 四个键。"
        "article 逐字包含四个选项和四个结果，不少于300个非空白字符，每行不超过20字。"
        "title 12～26字，short_title 6～16字，hashtags 恰好4项；"
        "cover_lines 1～3行，cover_highlights 1～3项且原样出现在 title 中。"
    )
    if feedback:
        user_prompt += f"\n上一次程序校验失败，必须修正：{feedback}"
    return json_text(qwen(
        "你是生活化心理测试短视频编辑。第一句必须直说心理测试并制造强烈悬念；只输出有效 JSON。",
        user_prompt,
        json_output=True,
        max_tokens=6000,
    ))


def _select_videos(search_context: dict) -> list[dict]:
    searches = search_context.get("searches") or []
    compact = []
    for search in searches:
        compact.append({
            "video_id": search["video_id"],
            "subtitle": search["subtitle"],
            "query": search["query"],
            "candidates": [
                {
                    "provider": row["provider"],
                    "id": row["id"],
                    "title": row["title"],
                    "duration": row["duration"],
                    "width": row["width"],
                    "height": row["height"],
                }
                for row in search.get("candidates") or []
            ],
        })
    payload = json_text(qwen(
        "你是心理测试短视频素材导演，只输出有效 JSON。",
        "根据字幕、英文检索词和候选标题，为每个镜头选择生活动作最贴近的视频。\n"
        f"候选：{json.dumps(compact, ensure_ascii=False)}\n"
        "输出 {\"selections\":[{\"video_id\":\"shot-001\",\"provider\":\"pexels\",\"id\":\"123\"}]}，覆盖全部镜头。",
        json_output=True,
        max_tokens=3000,
    ))
    selected = payload.get("selections")
    if not isinstance(selected, list):
        raise ValueError("千问选视频结果缺少 selections 数组")
    expected = {str(item["video_id"]) for item in searches}
    actual = {str(item.get("video_id") or "") for item in selected}
    if actual != expected:
        raise ValueError("千问选视频结果没有完整覆盖全部镜头")
    return selected


async def run(requested_topic: str = "", publish_date: str = "") -> dict:
    publish_date = resolve_publish_date(publish_date)
    async with ProjectMCP("core.mcp.psychology_quiz", PROJECT_ROOT) as mcp:
        prompt_context = await mcp.call("psychology_quiz_get_prompt")
        last_error = None
        for _ in range(3):
            try:
                generated = _generate_quiz(
                    prompt_context["quiz_prompt"],
                    prompt_context.get("recent_topics") or [],
                    requested_topic,
                    str(last_error) if last_error else "",
                )
                draft = await mcp.call("psychology_quiz_save_draft", {
                    "topic": generated["topic"],
                    "quiz": generated["quiz"],
                    "article": generated["article"],
                    "title": generated["title"],
                    "short_title": generated["short_title"],
                    "hashtags": generated["hashtags"],
                    "cover_lines": generated["cover_lines"],
                    "cover_highlights": generated["cover_highlights"],
                    "publish_date": publish_date,
                })
                topic = str(generated["topic"])
                break
            except (KeyError, ValueError, MCPCallError) as exc:
                last_error = exc
        else:
            raise RuntimeError(f"心理测试连续三次不合格：{last_error}")

        started = await mcp.call("psychology_quiz_start_storyboard", {
            "draft_path": draft["draft_path"],
            "tts_config": TTS_CONFIG,
        })
        storyboard_context = await mcp.poll("psychology_quiz_poll_task", started["task_path"])
        storyboard_prompt = storyboard_context["storyboard_prompt"]
        last_error = None
        for _ in range(3):
            storyboard = qwen(
                "你是严格的心理测试视频分镜导演，只输出规定格式的 VIDEO 和 SUB 行。",
                storyboard_prompt,
                max_tokens=14000,
            )["text"]
            try:
                started = await mcp.call("psychology_quiz_start_video_search", {
                    "draft_path": draft["draft_path"],
                    "storyboard_text": storyboard,
                    "video_config": {
                        "orientation": "landscape",
                        "per_provider": 8,
                        "providers": ["pexels", "pixabay", "coverr"],
                    },
                })
                prepared = await mcp.poll("psychology_quiz_poll_task", started["task_path"])
                break
            except MCPCallError as exc:
                last_error = exc
                storyboard_prompt += f"\n\n上一次输出校验失败，必须修正：{exc}"
        else:
            raise RuntimeError(f"心理测试分镜连续三次不合格：{last_error}")

        started = await mcp.call("psychology_quiz_start_download_videos", {
            "context_path": prepared["context_path"],
            "selections": _select_videos(prepared),
        })
        video_manifest = await mcp.poll("psychology_quiz_poll_task", started["task_path"])
        intro_prompt = str(prepared.get("intro_image_prompt") or "").strip()
        if not intro_prompt:
            raise RuntimeError("心理测试视频搜索结果缺少片头写实图 Prompt")
        intro_image = generate_qwen_image(
            intro_prompt,
            Path(draft["cache_dir"]) / "intro-realistic.png",
            size="1920x1080",
            cache_signature=hashlib.sha256(intro_prompt.encode("utf-8")).hexdigest(),
        )
        production_config = {**PRODUCTION_CONFIG, "bgm_path": random.choice(BGM_PATHS)}
        started = await mcp.call("psychology_quiz_start_finish_video", {
            "draft_path": draft["draft_path"],
            "video_manifest_path": video_manifest["manifest_path"],
            "intro_image_path": intro_image["output_path"],
            "production_config": production_config,
            "storyboard_text": storyboard,
            "production_source": "github_workflow",
        })
        manifest = await mcp.poll("psychology_quiz_poll_task", started["task_path"])

    remote = upload_run_files(
        "psychology_quiz",
        manifest["run_id"],
        [
            manifest["video_path"], manifest["cover_path"], manifest["title_path"],
            manifest["short_title_path"], manifest["publish_copy_path"],
            manifest["attribution_comment_path"], manifest["intro_image_path"],
        ],
        manifest,
    )
    uploaded_by_name = {
        str(item.get("source_name") or ""): str(item.get("url") or "")
        for item in remote.get("files") or []
    }
    video_url = uploaded_by_name.get(Path(manifest["video_path"]).name, "")
    if not video_url:
        raise RuntimeError("心理测试成片已上传，但 R2 返回结果缺少视频地址")
    production_outputs = commit_production_outputs([{
        "production_id": f"github_workflow:psychology_quiz:{manifest['run_id']}:scenario_quiz:1",
        "run_id": manifest["run_id"],
        "publish_date": manifest["publish_date"],
        "business_line": "psychology_quiz",
        "content_kind": "scenario_quiz",
        "content_part": 1,
        "title": manifest["title"],
        "hashtags": " ".join(f"#{str(tag).lstrip('#')}" for tag in manifest.get("hashtags") or []),
        "source": "github_workflow",
        "local_path": None,
        "r2_url": video_url,
        "r2_expires_at": None,
    }])
    write_summary("心理测试成片已生成", [
        ("话题", topic),
        ("标题", manifest["title"]),
        ("视频来源", "Pexels → Pixabay → Coverr 逐镜头兜底"),
        ("R2 清单", remote["manifest"]["url"]),
        ("平台发布", "未执行"),
    ])
    return {"manifest": manifest, "r2": remote, "production_outputs": production_outputs}
