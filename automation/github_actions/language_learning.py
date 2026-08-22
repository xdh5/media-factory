"""语言学习 GitHub Action：生成中英、韩英词汇成片。"""

from __future__ import annotations

import json
import shutil
import tempfile
from pathlib import Path

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
    """兼容原有单命令入口：依次制作、交接并上传 R2。"""
    with tempfile.TemporaryDirectory(prefix="language-learning-") as temporary_dir:
        root = Path(temporary_dir)
        state_path = root / "state.json"
        handoff_dir = root / "handoff"
        await generate_words(requested_topic, modes or ["en-zh", "en-ko"], state_path)
        await generate_cards(state_path)
        await generate_videos(state_path, handoff_dir)
        return upload_handoff(handoff_dir)


def _read_state(state_path: str | Path) -> dict:
    path = Path(state_path).resolve()
    payload = json.loads(path.read_text(encoding="utf-8"))
    if not isinstance(payload, dict):
        raise RuntimeError(f"语言学习阶段状态不是 JSON 对象：{path}")
    return payload


def _write_state(state_path: str | Path, payload: dict) -> None:
    path = Path(state_path).resolve()
    path.parent.mkdir(parents=True, exist_ok=True)
    path.write_text(json.dumps(payload, ensure_ascii=False, indent=2), encoding="utf-8")


async def generate_words(
    requested_topic: str,
    modes: list[str],
    state_path: str | Path,
) -> dict:
    """第一段：选题、占坑并生成通过校验的双语词表。"""
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
                "你是语言学习词表编辑。只输出用户规定的纯文本表格；第一行必须是“英文主题｜自然英语主题名称”，禁止 Markdown、标题、解释或省略首行。",
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
    state = {
        "topic": topic,
        "learning_modes": learning_modes,
        "run_id": run_id,
        "words": words,
    }
    _write_state(state_path, state)
    return state


async def generate_cards(state_path: str | Path) -> dict:
    """第二段：生成主体图并合成各语言方向的固定模板卡片。"""
    state = _read_state(state_path)
    topic = str(state["topic"])
    learning_modes = list(state["learning_modes"])
    run_id = str(state["run_id"])
    words = dict(state["words"])
    async with ProjectMCP("core.mcp.language_learning", PROJECT_ROOT) as mcp:
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
    state["card_dirs"] = card_dirs
    _write_state(state_path, state)
    return state


async def generate_videos(state_path: str | Path, handoff_dir: str | Path) -> dict:
    """第三段：配音合成成片，并整理供下一 Job 使用的临时交接目录。"""
    state = _read_state(state_path)
    topic = str(state["topic"])
    learning_modes = list(state["learning_modes"])
    run_id = str(state["run_id"])
    words = dict(state["words"])
    card_dirs = dict(state["card_dirs"])
    async with ProjectMCP("core.mcp.language_learning", PROJECT_ROOT) as mcp:
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
    destination = Path(handoff_dir).resolve()
    files_dir = destination / "files"
    files_dir.mkdir(parents=True, exist_ok=True)
    video_files = []
    for source_value in [path for video in manifest["videos"] for path in video["output_paths"]]:
        source = Path(source_value).resolve()
        target = files_dir / source.name
        shutil.copy2(source, target)
        video_files.append(str(target.relative_to(destination)))
    publish_manifest_file = ""
    if manifest.get("manifest_path"):
        source = Path(str(manifest["manifest_path"])).resolve()
        target = files_dir / source.name
        shutil.copy2(source, target)
        publish_manifest_file = str(target.relative_to(destination))
    handoff = {
        "workflow": "language_learning",
        "run_id": run_id,
        "topic": topic,
        "learning_modes": learning_modes,
        "video_files": video_files,
        "publish_manifest_file": publish_manifest_file,
        "manifest": manifest,
    }
    _write_state(destination / "handoff.json", handoff)
    return handoff


def upload_handoff(handoff_dir: str | Path) -> dict:
    """读取上一 Job 的临时交接文件，将成片和发布清单上传 R2。"""
    destination = Path(handoff_dir).resolve()
    handoff = _read_state(destination / "handoff.json")
    video_paths = [destination / value for value in handoff["video_files"]]
    publish_manifest_path = (
        destination / handoff["publish_manifest_file"]
        if handoff.get("publish_manifest_file")
        else None
    )
    manifest = dict(handoff["manifest"])
    manifest["output_dir"] = str(destination)
    remote = upload_run_files(
        "language_learning",
        str(handoff["run_id"]),
        video_paths,
        manifest,
        publish_manifest_path=publish_manifest_path,
    )
    write_summary(
        "语言学习成片已生成并上传 R2",
        [
            ("主题", str(handoff["topic"])),
            ("模式", ", ".join(handoff["learning_modes"])),
            ("R2 清单", remote["manifest"]["url"]),
        ],
    )
    return {"manifest": manifest, "r2": remote}
