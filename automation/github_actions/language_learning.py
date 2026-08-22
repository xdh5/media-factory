"""语言学习 GitHub Action：生成中英、韩英词汇成片。"""

from __future__ import annotations

import json

from ._mcp import MCPCallError, ProjectMCP
from ._shared import PROJECT_ROOT, qwen, upload_run_files, write_summary


VOICES = {"en": "en-US-AriaNeural", "zh": "zh-CN-XiaoxiaoNeural", "ko": "ko-KR-SunHiNeural"}


def _choose_topic(recent_topics: list[str], requested_topic: str) -> str:
    if requested_topic.strip():
        return requested_topic.strip()
    return str(qwen(
        "你是语言学习短视频选题编辑，只返回一个简短中文主题，不加说明。",
        "选择适合初学者学习10个生活常用词的具体主题。"
        f"不得与最近30天主题重复：{json.dumps(recent_topics, ensure_ascii=False)}",
        max_tokens=80,
    )["text"]).strip().strip("“”\"'")


def _publish_config(topic: str, modes: list[str]) -> dict:
    result = {}
    if "en-zh" in modes:
        result["en-zh"] = {
            "account_group": "Daily Chinese Learning",
            "youtube_account": "language_learning",
            "tags": ["#learnchinese", "#chinesevocabulary", "#mandarinchinese", "#dailychinese"],
            "short_title": f"中文{topic}怎么说",
        }
    if "en-ko" in modes:
        result["en-ko"] = {
            "account_group": "韩语",
            "tags": ["#学韩语", "#韩语单词", "#韩语入门", "#每日韩语"],
            "short_title": "韩语单词怎么说",
            "platforms": ["dy", "ks", "blbl", "bjh", "tt", "sph"],
        }
    return result


async def run(requested_topic: str = "", modes: list[str] | None = None) -> dict:
    learning_modes = modes or ["en-zh", "en-ko"]
    async with ProjectMCP("core.mcp.language_learning", PROJECT_ROOT) as mcp:
        topics = await mcp.call("language_learning_get_topics")
        topic = _choose_topic(topics.get("recent_topics") or [], requested_topic)
        occupied = await mcp.call(
            "language_learning_occupy_topic",
            {"topic": topic, "learning_modes": learning_modes},
        )
        run_id = occupied["run_id"]
        prompt = await mcp.call(
            "language_learning_build_vocabulary_prompt",
            {"topic": topic, "learning_modes": learning_modes},
        )
        last_error = None
        for _ in range(3):
            response_text = qwen(
                "你是语言学习词表编辑，只输出用户规定的纯文本表格。",
                prompt["user_prompt"],
                max_tokens=2500,
            )["text"]
            try:
                words = await mcp.call(
                    "language_learning_parse_vocabulary_response",
                    {
                        "response_text": response_text,
                        "learning_modes": learning_modes,
                        "topic": topic,
                        "run_id": run_id,
                    },
                )
                break
            except MCPCallError as exc:
                last_error = exc
                prompt["user_prompt"] += f"\n\n上一次词表校验失败，必须换词并修正：{exc}"
        else:
            raise RuntimeError(f"语言词表连续三次不合格：{last_error}")
        primary_words = words.get("en-zh") or words.get("en-ko")
        prepared = await mcp.call(
            "language_learning_prepare_images",
            {"topic": topic, "words": primary_words, "run_id": run_id},
        )
        started = await mcp.call(
            "language_learning_start_submit_images",
            {
                "context_path": prepared["context_path"],
                "images": [],
                "run_id": run_id,
                "failures": [{"image_id": "subject-sheet", "attempts": 0, "capability_unavailable": True, "errors": ["GitHub Runner 无宿主生图能力"]}],
            },
        )
        submitted = await mcp.poll("language_learning_poll_task", started["task_path"])
        card_dirs = {}
        for mode in learning_modes:
            started = await mcp.call(
                "language_learning_start_compose_cards",
                {
                    "subject_sheet_path": submitted["subject_sheet_path"],
                    "words": words[mode],
                    "learning_mode": mode,
                    "topic_english": words["_topic_english"],
                    "run_id": run_id,
                },
            )
            cards = await mcp.poll("language_learning_poll_task", started["task_path"])
            card_dirs[mode] = cards["output_dir"]
        started = await mcp.call(
            "language_learning_start_create_videos",
            {
                "card_dirs": card_dirs,
                "words_by_mode": {mode: words[mode] for mode in learning_modes},
                "run_id": run_id,
                "voices": VOICES,
                "publish_config": _publish_config(topic, learning_modes),
                "topic": topic,
                "language_pause": 0.3,
                "word_pause": 0.3,
            },
        )
        manifest = await mcp.poll("language_learning_poll_task", started["task_path"])
    video_paths = [path for video in manifest["videos"] for path in video["output_paths"]]
    remote = upload_run_files(
        "language_learning",
        run_id,
        video_paths,
        manifest,
        publish_manifest_path=manifest.get("manifest_path"),
    )
    write_summary(
        "语言学习成片已生成，等待手动确认发布",
        [("主题", topic), ("模式", ", ".join(learning_modes)), ("R2 清单", remote["manifest"]["url"])],
    )
    return {"manifest": manifest, "r2": remote}
