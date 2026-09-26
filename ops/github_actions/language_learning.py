"""语言学习 GitHub Action：生成中英、韩英词汇成片，不发布平台。"""

from __future__ import annotations

import json
import re
import shutil
from pathlib import Path
from urllib.parse import unquote, urlparse

from ._mcp import MCPCallError, ProjectMCP
from core.tools.r2_storage import download_public_file

from ._shared import (
    PROJECT_ROOT,
    qwen,
    qwen_vision,
    upload_diagnostic_files,
    write_summary,
)


def _compact_publish_row(row: dict) -> dict:
    video = row.get("video") if isinstance(row.get("video"), dict) else {}
    result = row.get("result") if isinstance(row.get("result"), dict) else {}
    return {
        "channel": row.get("channel"),
        "part": row.get("part"),
        "success": row.get("success"),
        "title": video.get("title") or row.get("title"),
        "video_url": video.get("video_url"),
        "error": row.get("error"),
        "status": result.get("status"),
        "post_id": result.get("post_id"),
        "video_id": result.get("video_id"),
    }


def _log_publish_batches(batches: list) -> None:
    for batch in batches:
        if not isinstance(batch, dict):
            continue
        rows = [_compact_publish_row(row) for row in (batch.get("results") or []) if isinstance(row, dict)]
        print(
            f"[语言发布结果] channel={batch.get('channel')} format={batch.get('video_format')} "
            f"success={batch.get('success')} rows={json.dumps(rows, ensure_ascii=False)}",
            flush=True,
        )


def _publish_failure_payload(result: dict) -> dict:
    return {
        "success": result.get("success"),
        "completed_targets": result.get("completed_targets"),
        "published": [
            {
                "channel": batch.get("channel"),
                "video_format": batch.get("video_format"),
                "success": batch.get("success"),
                "results": [
                    _compact_publish_row(row)
                    for row in (batch.get("results") or [])
                    if isinstance(row, dict)
                ],
            }
            for batch in (result.get("published") or [])
            if isinstance(batch, dict)
        ],
    }


async def _choose_topic(mcp: ProjectMCP, recent_topics: list[str], requested_topic: str, attempts: int) -> str:
    feedback = ""
    for _ in range(attempts):
        prompt = await mcp.call("language_learning_get_topic_generation_prompt", {
            "recent_topics": recent_topics, "requested_topic": requested_topic, "feedback": feedback,
        })
        response = qwen(prompt["system_prompt"], prompt["user_prompt"], max_tokens=30)["text"]
        try:
            result = await mcp.call("language_learning_validate_topic_response", {
                "response_text": response, "recent_topics": recent_topics,
            })
            return str(result["topic"])
        except MCPCallError as exc:
            feedback = str(exc)
    raise RuntimeError(f"语言学习主题连续 {attempts} 次不合格：{feedback}")


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
        "topic": topic,
        "learning_modes": learning_modes,
        "publish_date": publish_date,
        "run_id": run_id,
        "words": words,
        "pack_id": pack["pack_id"],
        "pack_image_urls": list(pack["image_urls"]),
    }
    _write_state(state_path, state)
    return state


def _write_diagnostics(diagnostics_dir: Path, payload: dict) -> None:
    diagnostics_dir.mkdir(parents=True, exist_ok=True)
    (diagnostics_dir / "diagnostics.json").write_text(
        json.dumps(payload, ensure_ascii=False, indent=2),
        encoding="utf-8",
    )


async def _visual_layout(mcp: ProjectMCP, subject_sheet_path: str, feedback: list[str]) -> dict:
    """只让千问视觉提取抠图所需的十个坐标，不承担内容质检。"""
    prompt = await mcp.call("language_learning_get_visual_validation_prompt")
    user_prompt = str(prompt["user_prompt"])
    if feedback:
        user_prompt += "\n\n上一次坐标不可用，请重新观察原图并给出更保守、更准确的完整十框：\n- " + "\n- ".join(feedback)
    return qwen_vision(subject_sheet_path, str(prompt["system_prompt"]), user_prompt)


def _inspect_background_removed_sheet(path: str, prompt: dict, feedback: list[str]) -> dict:
    user_prompt = str(prompt["user_prompt"])
    if feedback:
        user_prompt += "\n\n上一次整图验收失败，必须修正：\n- " + "\n- ".join(feedback)
    result = qwen_vision(path, str(prompt["system_prompt"]), user_prompt)
    valid = result.get("valid")
    if not isinstance(valid, bool):
        raise RuntimeError("千问没有正确判断整图验收结果")
    failure_kind = str(result.get("failure_kind") or "").strip().casefold()
    if not valid and not failure_kind:
        failure_kind = "completeness"
    return {
        "valid": valid,
        "failure_kind": "" if valid else failure_kind,
        "issue": str(result.get("issue") or "").strip(),
        "subject_count": result.get("subject_count"),
    }


async def generate_cards(
    state_path: str | Path,
    diagnostics_dir: str | Path = "cache/github_actions/language-learning-diagnostics",
) -> dict:
    """第二段：下载已验收的十张透明主体图，直接拼卡。"""
    state = _read_state(state_path)
    topic = str(state["topic"])
    learning_modes = list(state["learning_modes"])
    run_id = str(state["run_id"])
    words = dict(state["words"])
    pack_urls = list(state.get("pack_image_urls") or [])
    if len(pack_urls) != 1:
        raise RuntimeError("GitHub 语言生产只能使用一张已验收的十元素透明主题图")
    pack_root = Path(diagnostics_dir).resolve().parent / "pack-subjects" / run_id
    subject_sheet_path = pack_root / "subject-sheet.png"
    key = unquote(urlparse(str(pack_urls[0])).path).lstrip("/")
    download_public_file(key, subject_sheet_path)
    card_dirs = {}
    async with ProjectMCP("core.mcp.language_learning", PROJECT_ROOT) as mcp:
        layout = await _visual_layout(mcp, str(subject_sheet_path), [])
        validation = await mcp.call("language_learning_validate_subject_sheet", {
            "subject_sheet_path": str(subject_sheet_path), "visual_layout": layout, "run_id": run_id,
        })
        if validation.get("valid") is not True:
            raise RuntimeError(f"词包主题图裁切失败：{'；'.join(validation.get('issues') or [])}")
        sheet_prompt = await mcp.call("language_learning_get_sheet_validation_prompt")
        target_words = "、".join(str(item.get("english") or "").strip() for item in words["en-zh"])
        sheet_prompt = {
            **sheet_prompt,
            "user_prompt": (
                f"{sheet_prompt['user_prompt']}\n\n"
                f"本期禁止直接写入画面的目标英语词为：{target_words}。"
                "其他与这些目标词无关的自然场景文字允许存在，不能仅因它们存在而判定 text 失败。"
            ),
        }
        sheet_review = _inspect_background_removed_sheet(
            str(validation["background_removed_sheet_path"]), sheet_prompt, [],
        )
        review = await mcp.call("language_learning_review_subject_sheet", {
            "subject_sheet_path": str(subject_sheet_path), "review": sheet_review, "run_id": run_id,
        })
        if review.get("approved") is not True:
            raise RuntimeError(f"词包主题图整图验收失败：{'；'.join(review.get('validation_issues') or [])}")
        for mode in learning_modes:
            started = await mcp.call("language_learning_start_compose_cards", {
                "subject_sheet_path": str(subject_sheet_path), "words": words[mode], "learning_mode": mode,
                "topic_english": words["_topic_english"], "run_id": run_id,
            })
            cards = await mcp.poll("language_learning_poll_task", started["task_path"])
            card_dirs[mode] = cards["output_dir"]
    state["subject_sheet_path"] = str(subject_sheet_path)
    state["subject_sheet_validation"] = {**validation, "review": sheet_review}
    state["card_dirs"] = card_dirs
    _write_state(state_path, state)
    return state

    diagnostic_root = Path(diagnostics_dir).resolve()
    diagnostic_payload = {
        "workflow": "language_learning",
        "run_id": run_id,
        "topic": topic,
        "status": "running",
        "attempts": [],
    }
    _write_diagnostics(diagnostic_root, diagnostic_payload)
    approved_validation = None
    submitted = None
    async with ProjectMCP("core.mcp.language_learning", PROJECT_ROOT) as mcp:
        config = await mcp.call("language_learning_get_production_config", {
            "topic": topic, "learning_modes": learning_modes,
        })
        primary_words = words.get("en-zh") or words.get("en-ko")
        sheet_prompt = await mcp.call("language_learning_get_sheet_validation_prompt")
        generation_issues: list[str] = []
        max_attempts = int(config["subject_generation_max_attempts"])
        for generation_attempt in range(1, max_attempts + 1):
            prepared = await mcp.call(
                "language_learning_prepare_images",
                {
                    "topic": topic,
                    "words": primary_words,
                    "run_id": run_id,
                    "force_images": generation_attempt > 1,
                    "generation_attempt": generation_attempt,
                    "validation_issues": generation_issues,
                },
            )
            started = await mcp.call(
                "language_learning_start_submit_images",
                {
                    "context_path": prepared["context_path"],
                    "images": [],
                    "run_id": run_id,
                    "generation_attempt": generation_attempt,
                    "failures": [{
                        "image_id": "subject-sheet",
                        "attempts": 0,
                        "capability_unavailable": True,
                        "errors": ["GitHub Runner 无宿主生图能力，使用项目千问兜底"],
                    }],
                },
            )
            submitted = await mcp.poll("language_learning_poll_task", started["task_path"])
            visual_feedback: list[str] = []
            generation_issues = []
            for visual_round in range(1, 3):
                layout = await _visual_layout(mcp, submitted["subject_sheet_path"], visual_feedback)
                validation = await mcp.call(
                    "language_learning_validate_subject_sheet",
                    {
                        "subject_sheet_path": submitted["subject_sheet_path"],
                        "visual_layout": layout,
                        "run_id": run_id,
                    },
                )
                if validation.get("valid") is not True:
                    visual_feedback = [str(item) for item in validation.get("issues") or []]
                    continue
                background_removed_path = str(validation.get("background_removed_sheet_path") or "").strip()
                if not background_removed_path:
                    visual_feedback = ["Python 未生成去背景后的完整主题图"]
                    continue
                sheet_review = _inspect_background_removed_sheet(
                    background_removed_path,
                    sheet_prompt,
                    visual_feedback,
                )
                review = await mcp.call(
                    "language_learning_review_subject_sheet",
                    {
                        "subject_sheet_path": submitted["subject_sheet_path"],
                        "review": sheet_review,
                        "run_id": run_id,
                    },
                )
                if review.get("approved") is True:
                    approved_validation = {**validation, "review": sheet_review, "visual_round": visual_round}
                    break
                visual_feedback = list(review.get("validation_issues") or [])
                if review.get("action") == "regenerate":
                    generation_issues = visual_feedback
                    break
            if approved_validation is not None:
                break
            if not generation_issues:
                generation_issues = visual_feedback or ["视觉验收未通过"]
            background_removed_path = str(
                (validation or {}).get("background_removed_sheet_path") or ""
            ).strip()
            if not background_removed_path:
                raise RuntimeError("主体图验收失败，但没有生成可上传的去背景色主题图")
            source = Path(background_removed_path).resolve()
            if not source.is_file():
                raise RuntimeError(f"去背景色主题图不存在，无法保存失败诊断：{source}")
            failed_image = diagnostic_root / f"subject-sheet-attempt-{generation_attempt}{source.suffix.lower() or '.png'}"
            shutil.copy2(source, failed_image)
            diagnostic_payload["attempts"].append({
                "generation_attempt": generation_attempt,
                "file": failed_image.name,
                "source_stage": "background_removed",
                "issues": generation_issues,
            })
            diagnostic_payload["status"] = "retrying"
            _write_diagnostics(diagnostic_root, diagnostic_payload)
        else:
            diagnostic_payload["status"] = "failed"
            _write_diagnostics(diagnostic_root, diagnostic_payload)
            details = "；".join(generation_issues) or "没有返回具体视觉错误"
            raise RuntimeError(f"原始主题图连续 {max_attempts} 次未通过检查：{details}")
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
    state["subject_sheet_path"] = submitted["subject_sheet_path"]
    state["subject_sheet_validation"] = {**approved_validation, "generation_attempt": generation_attempt}
    state["card_dirs"] = card_dirs
    diagnostic_payload["status"] = "succeeded"
    _write_diagnostics(diagnostic_root, diagnostic_payload)
    _write_state(state_path, state)
    return state


def _source_words(manifest: dict) -> dict:
    """从旧成片清单恢复中英、韩英两套原始词表。"""
    by_mode = {str(item.get("learning_mode") or ""): item for item in manifest.get("videos") or []}
    result = {"_topic_english": str(manifest.get("topic") or "").strip()}
    for mode in ("en-zh", "en-ko"):
        timeline = by_mode.get(mode, {}).get("timeline") or []
        if len(timeline) != 10:
            raise RuntimeError(f"旧 R2 清单的 {mode} 词表不是 10 个词，不能原样重组")
        result[mode] = [
            {
                "english": str(item.get("english") or "").strip(),
                "chinese": str(item.get("chinese") or "").strip(),
                "korean": str(item.get("korean") or "").strip(),
                "romanization": str(item.get("romanization") or "").strip(),
            }
            for item in timeline
        ]
    return result


async def recompose_cards_from_r2(
    source_run_id: str,
    state_path: str | Path,
    publish_date: str = "",
) -> dict:
    """复用旧 R2 主题图、词表和视觉框，只重新拼卡与出片。"""
    source_id = str(source_run_id or "").strip()
    if not re.fullmatch(r"run-\d+", source_id):
        raise ValueError("source_run_id 必须是 run-数字 格式")
    source_prefix = f"runs/language_learning/{source_id}"
    source_root = PROJECT_ROOT / "cache" / "github_actions" / "recompose-source" / source_id
    source_manifest_path = source_root / "r2-manifest.json"
    source_sheet_path = source_root / "subject-sheet.png"
    download_public_file(f"{source_prefix}/r2-manifest.json", source_manifest_path)
    download_public_file(f"{source_prefix}/subject-sheet.png", source_sheet_path)
    source_manifest = _read_state(source_manifest_path)
    topic = str(source_manifest.get("topic") or "").strip()
    words = _source_words(source_manifest)
    modes = [mode for mode in ("en-zh", "en-ko") if mode in words]
    source_validation = dict(source_manifest.get("subject_sheet_validation") or {})
    visual_layout = dict(source_validation.get("vision") or {})
    source_review = dict(source_validation.get("review") or {})
    source_reviews = list(source_validation.get("reviews") or [])
    if not str(publish_date or "").strip():
        raise ValueError("重组语言学习成片必须明确传入 publish_date")
    has_legacy_review = (
        len(source_reviews) == 10
        and all(item.get("valid") is True for item in source_reviews)
    )
    if not visual_layout or (source_review.get("valid") is not True and not has_legacy_review):
        raise RuntimeError("旧 R2 清单缺少视觉框或整图验收结果，不能安全原样重组")
    async with ProjectMCP("core.mcp.language_learning", PROJECT_ROOT) as mcp:
        occupied = await mcp.call(
            "language_learning_occupy_topic",
            {"topic": topic, "learning_modes": modes, "publish_date": publish_date},
        )
        run_id = str(occupied["run_id"])
        validation = await mcp.call(
            "language_learning_validate_subject_sheet",
            {
                "subject_sheet_path": str(source_sheet_path),
                "visual_layout": visual_layout,
                "run_id": run_id,
            },
        )
        if validation.get("valid") is not True:
            raise RuntimeError(f"旧主题图重新抠图失败：{'；'.join(validation.get('issues') or [])}")
        approved_review = source_review if source_review.get("valid") is True else {
            "valid": True,
            "failure_kind": "",
            "issue": "复用旧成片已通过的整图验收",
        }
        review = await mcp.call(
            "language_learning_review_subject_sheet",
            {
                "subject_sheet_path": str(source_sheet_path),
                "review": approved_review,
                "run_id": run_id,
            },
        )
        if review.get("approved") is not True:
            raise RuntimeError("旧主题图的整图验收未能重新批准")
        card_dirs = {}
        for mode in modes:
            started = await mcp.call(
                "language_learning_start_compose_cards",
                {
                    "subject_sheet_path": str(source_sheet_path),
                    "words": words[mode],
                    "learning_mode": mode,
                    "topic_english": words["_topic_english"],
                    "run_id": run_id,
                },
            )
            cards = await mcp.poll("language_learning_poll_task", started["task_path"])
            card_dirs[mode] = cards["output_dir"]
    state = {
        "topic": topic,
        "learning_modes": modes,
        "publish_date": publish_date,
        "run_id": run_id,
        "words": words,
        "subject_sheet_path": str(source_sheet_path),
        "subject_sheet_validation": {
            **validation,
            "review": approved_review,
            "source_run_id": source_id,
            "recomposed": True,
        },
        "card_dirs": card_dirs,
    }
    _write_state(state_path, state)
    return state


def upload_failed_subject_sheets(diagnostics_dir: str | Path) -> dict:
    """上传被视觉验收拒绝的去背景色主题图；没有失败图时跳过。"""
    root = Path(diagnostics_dir).resolve()
    metadata_path = root / "diagnostics.json"
    if not metadata_path.is_file():
        return {"status": "skipped", "reason": "本次任务没有主体图诊断记录"}
    metadata = _read_state(metadata_path)
    paths = [root / str(item["file"]) for item in metadata.get("attempts") or []]
    paths = [path for path in paths if path.is_file()]
    if not paths:
        return {"status": "skipped", "reason": "本次任务没有校验失败的去背景色主题图"}
    result = upload_diagnostic_files("language_learning", str(metadata["run_id"]), paths, metadata)
    write_summary(
        "语言学习失败去背景色主题图已上传 R2",
        [("主题", str(metadata["topic"])), ("失败图片数", str(len(paths))), ("图片阶段", "去背景色后"), ("保留时间", "1 天"), ("R2 诊断清单", str(result["manifest"]["url"]))],
    )
    return {"status": "uploaded", "r2": result}


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
                "learning_modes": list(handoff["learning_modes"]),
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
    manifest_url: str,
    run_id: str,
    *,
    targets: list[str] | None = None,
) -> dict:
    """按语言学习 MCP 配置，把尚未发布的平台排到计划发布日期的指定北京时间。"""
    async with ProjectMCP("core.mcp.language_learning", PROJECT_ROOT) as mcp:
        schedule = await mcp.call("language_learning_get_publish_schedule", {"run_id": run_id})
    publish_at = str(schedule["publish_at"])
    selected_targets = [
        str(item).strip().casefold()
        for item in (targets or schedule["targets"])
        if str(item).strip()
    ]
    unknown = set(selected_targets) - set(schedule["targets"])
    if unknown:
        raise RuntimeError(f"不支持的语言学习发布平台：{', '.join(sorted(unknown))}")
    if not selected_targets:
        return {"success": True, "skipped": True, "reason": "该计划发布日期四个平台都已有发布记录"}
    async with ProjectMCP("core.mcp.language_learning", PROJECT_ROOT) as mcp:
        started = await mcp.call(
            "language_learning_start_publish",
            {
                "manifest_path": str(manifest_url),
                "publish_confirmed": True,
                "run_id": str(run_id),
                "targets": selected_targets,
                "publish_at": publish_at,
            },
        )
        result = await mcp.poll("language_learning_poll_task", started["task_path"])
    _log_publish_batches(result.get("published") or [])
    if result.get("success") is not True:
        raise RuntimeError(f"四平台排期存在失败：{json.dumps(_publish_failure_payload(result), ensure_ascii=False)}")
    completed_channels = {
        str(item).strip().casefold()
        for item in result.get("completed_targets") or []
        if str(item).strip()
    }
    if not completed_channels:
        completed_channels = {
            str(item.get("channel") or "").strip().casefold()
            for item in result.get("published") or []
            if item.get("success") is True
        }
    missing_channels = set(selected_targets) - completed_channels
    if missing_channels:
        raise RuntimeError(f"四平台排期返回不完整，缺少：{', '.join(sorted(missing_channels))}")
    return {"publish_at": publish_at, **result}
