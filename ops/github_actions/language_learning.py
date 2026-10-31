"""语言学习 GitHub Action：生成中英、韩英词汇成片，不发布平台。"""

from __future__ import annotations

import json
import re
import shutil
from pathlib import Path
from urllib.parse import unquote, urlparse

from ._mcp import ProjectMCP
from core.tools.media_files import download_public_file

from ._shared import (
    PROJECT_ROOT,
    write_summary,
)


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
    publish_date: str = "",
    *,
    pending_outputs: list[dict] | None = None,
    completed_outputs: list[dict] | None = None,
) -> dict:
    """第一段：从已验收词包库存领取主题与双语词表。"""
    if not str(publish_date or "").strip():
        raise ValueError("GitHub 语言生产必须明确传入 publish_date")
    async with ProjectMCP("core.mcp.language_learning", PROJECT_ROOT) as mcp:
        claimed = await mcp.call("language_learning_claim_pack", {"publish_date": publish_date})
        pack = dict(claimed["pack"])
        topic, words, run_id = str(pack["topic"]), dict(pack["words"]), str(claimed["run_id"])
        learning_modes = list(modes or ["en-zh", "en-ko"])
    state = {
        "pending_outputs": pending_outputs,
        "topic": topic,
        "learning_modes": learning_modes,
        "publish_date": publish_date,
        "run_id": run_id,
        "words": words,
        "pack_id": pack["pack_id"],
        "pack_subject_urls": list(pack["image_urls"]),
    }
    if completed_outputs:
        config = await _production_config(topic, [])
        items = {}
        for row in completed_outputs:
            if row["run_id"] != run_id:
                continue
            kind = str(row["content_kind"])
            mode = kind.removesuffix("-quiz")
            video_format = "quiz" if kind.endswith("-quiz") else "standard"
            item = items.setdefault(kind, {
                "learning_mode": mode, "video_format": video_format,
                "title": row["title"], "tags": str(row.get("hashtags") or "").split(),
                "short_title": config["publish_config"].get(mode, {}).get("short_title", ""), "videos": [],
            })
            item["videos"].append({
                "content_part": int(row.get("content_part") or 1), "title": row["title"],
                "output_path": "", "video_url": row["r2_url"],
                "r2_key": unquote(urlparse(row["r2_url"]).path).lstrip("/"),
            })
        manifest_path = Path(claimed["output_dir"]) / "publish-manifest.json"
        _write_state(manifest_path, {"items": list(items.values())})
    _write_state(state_path, state)
    return state


async def _production_config(topic: str, modes: list[str]) -> dict:
    async with ProjectMCP("core.mcp.language_learning", PROJECT_ROOT) as mcp:
        return await mcp.call("language_learning_get_production_config", {"topic": topic, "learning_modes": modes})


async def generate_cards(
    state_path: str | Path,
    diagnostics_dir: str | Path = "cache/github_actions/language-learning-diagnostics",
) -> dict:
    """第二段：下载预制包中已验收的十张透明主体图，直接拼卡。"""
    state = _read_state(state_path)
    learning_modes = list(state["learning_modes"])
    run_id = str(state["run_id"])
    words = dict(state["words"])
    pack_urls = list(state.get("pack_subject_urls") or [])
    if len(pack_urls) != 10:
        raise RuntimeError("GitHub 语言生产必须使用十张已验收透明主体图")
    pack_root = Path(diagnostics_dir).resolve().parent / "pack-subjects" / run_id
    subject_paths = []
    for index, url in enumerate(pack_urls, 1):
        subject_path = pack_root / f"{index:02d}.png"
        key = unquote(urlparse(str(url)).path).lstrip("/")
        download_public_file(key, subject_path)
        subject_paths.append(str(subject_path))
    card_dirs = {}
    async with ProjectMCP("core.mcp.language_learning", PROJECT_ROOT) as mcp:
        for mode in learning_modes:
            started = await mcp.call("language_learning_start_compose_pack_cards", {
                "subject_image_paths": subject_paths, "words": words[mode], "learning_mode": mode,
                "topic_english": words["_topic_english"], "run_id": run_id,
            })
            cards = await mcp.poll("language_learning_poll_task", started["task_path"])
            card_dirs[mode] = cards["output_dir"]
    state["subject_image_paths"] = subject_paths
    state["card_dirs"] = card_dirs
    _write_state(state_path, state)
    return state
async def generate_videos(state_path: str | Path, handoff_dir: str | Path) -> dict:
    """第三段：配音合成成片，并整理供上传 Job 使用的临时目录。"""
    state = _read_state(state_path)
    topic = str(state["topic"])
    learning_modes = list(state["learning_modes"])
    run_id = str(state["run_id"])
    words = dict(state["words"])
    card_dirs = dict(state["card_dirs"])
    async with ProjectMCP("core.mcp.language_learning", PROJECT_ROOT) as mcp:
        config = await mcp.call("language_learning_get_production_config", {
            "topic": topic, "learning_modes": learning_modes,
        })
        started = await mcp.call(
            "language_learning_start_create_videos",
            {
                "card_dirs": card_dirs,
                "words_by_mode": {mode: words[mode] for mode in learning_modes},
                "run_id": run_id,
                "voices": config["voices"],
                "publish_config": config["publish_config"],
                "topic": topic,
                "language_pause": config["language_pause"],
                "word_pause": config["word_pause"],
                "production_source": "github_workflow",
                "video_formats": config["video_formats"],
                "pending_outputs": state.get("pending_outputs"),
            },
        )
        manifest = await mcp.poll("language_learning_poll_task", started["task_path"])
    manifest["subject_sheet_validation"] = dict(state.get("subject_sheet_validation") or {"source": "prebuilt_pack"})
    destination = Path(handoff_dir).resolve()
    files_dir = destination / "files"
    files_dir.mkdir(parents=True, exist_ok=True)
    subject_sheet_target = None
    if state.get("subject_sheet_path"):
        subject_sheet_source = Path(str(state["subject_sheet_path"])).resolve()
        subject_sheet_target = files_dir / f"subject-sheet{subject_sheet_source.suffix.lower() or '.png'}"
        shutil.copy2(subject_sheet_source, subject_sheet_target)
    video_files = []
    for source_value in [path for video in manifest["videos"] for path in video["output_paths"]]:
        source = Path(source_value).resolve()
        target = files_dir / source.name
        shutil.copy2(source, target)
        video_files.append(str(target.relative_to(destination)))
    metadata_file = ""
    if manifest.get("manifest_path"):
        source = Path(str(manifest["manifest_path"])).resolve()
        target = files_dir / source.name
        shutil.copy2(source, target)
        metadata_file = str(target.relative_to(destination))
    handoff = {
        "workflow": "language_learning",
        "run_id": run_id,
        "publish_date": str(state.get("publish_date") or ""),
        "topic": topic,
        "learning_modes": learning_modes,
        "subject_sheet_file": str(subject_sheet_target.relative_to(destination)) if subject_sheet_target else "",
        "video_files": video_files,
        "metadata_file": metadata_file,
        "manifest": manifest,
    }
    _write_state(destination / "handoff.json", handoff)
    return handoff


async def upload_handoff(handoff_dir: str | Path) -> dict:
    """读取上一 Job 的交接文件，将成片与元数据上传 R2。"""
    destination = Path(handoff_dir).resolve()
    handoff = _read_state(destination / "handoff.json")
    video_paths = [destination / value for value in handoff["video_files"]]
    subject_sheet_path = destination / handoff["subject_sheet_file"] if handoff.get("subject_sheet_file") else None
    metadata_path = destination / handoff["metadata_file"] if handoff.get("metadata_file") else None
    manifest = dict(handoff["manifest"])
    async with ProjectMCP("core.mcp.language_learning", PROJECT_ROOT) as mcp:
        started = await mcp.call(
            "language_learning_start_upload_r2",
            {
                "manifest_path": manifest["manifest_path"],
                "run_id": str(handoff["run_id"]),
                "subject_sheet_path": str(subject_sheet_path) if subject_sheet_path else None,
            },
        )
        remote = await mcp.poll("language_learning_poll_task", started["task_path"])
    download_urls = {}
    for item in remote.get("uploaded") or []:
        mode = str(item.get("learning_mode") or "").strip()
        if item.get("kind") == "video" and mode and mode not in download_urls:
            download_urls[mode] = str(item.get("url") or "")
    return {
        "run_id": str(handoff["run_id"]),
        "manifest": manifest,
        "r2": {"manifest": {"url": remote["manifest_url"]}},
        "production_outputs": remote.get("production_outputs") or [],
        "topic": str(handoff["topic"]),
        "subject_sheet_url": str(remote.get("subject_sheet_url") or ""),
        "download_urls": download_urls,
    }

async def schedule_publication(
    run_id: str,
    *,
    targets: list[str] | None = None,
) -> dict:
    """通过统一发布 MCP，把 GitHub/R2 成片排到计划发布日期北京时间 16:00。"""
    run_date = str(run_id).removeprefix("run-")
    if len(run_date) != 8 or not run_date.isdigit():
        raise RuntimeError(f"语言学习 run_id 格式错误：{run_id}")
    publish_date = f"{run_date[:4]}-{run_date[4:6]}-{run_date[6:]}"
    publish_at = f"{publish_date}T16:00:00+08:00"
    supported_targets = ["youtube", "tiktok", "instagram", "facebook"]
    selected_targets = [
        str(item).strip().casefold()
        for item in (targets or supported_targets)
        if str(item).strip()
    ]
    unknown = set(selected_targets) - set(supported_targets)
    if unknown:
        raise RuntimeError(f"不支持的语言学习发布平台：{', '.join(sorted(unknown))}")
    if not selected_targets:
        return {"success": True, "skipped": True, "reason": "该计划发布日期四个平台都已有发布记录"}
    async with ProjectMCP("core.mcp.publishing", PROJECT_ROOT) as mcp:
        started = await mcp.call(
            "publishing_start_publish",
            {
                "business_line": "language_learning",
                "publish_date": publish_date,
                "account_group": "chinese",
                "platforms": selected_targets,
                "content_kind": "en-zh",
                "publish_mode": "scheduled",
                "publish_at": publish_at,
            },
        )
        await mcp.poll("publishing_poll_task", started["task_path"])
        # 平台完整性校验使用完整回执，精简轮询结果仅用于进度显示。
        completed = await mcp.call("publishing_poll_task", {
            "task_path": started["task_path"], "detailed": True,
        })
        result = completed["result"]
    completed_channels = {
        str(item.get("record", {}).get("platform") or "").strip().casefold()
        for item in result.get("published") or []
    }
    completed_channels.update(
        str(item.get("platform") or "").strip().casefold()
        for item in result.get("skipped") or []
    )
    missing_channels = set(selected_targets) - completed_channels
    if missing_channels:
        raise RuntimeError(f"四平台排期返回不完整，缺少：{', '.join(sorted(missing_channels))}")
    return {"publish_at": publish_at, "run_id": run_id, **result}
