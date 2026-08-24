"""语言学习 GitHub Action：生成中英、韩英词汇成片，不发布平台。"""

from __future__ import annotations

import json
import re
import shutil
from datetime import datetime
from pathlib import Path
from zoneinfo import ZoneInfo

from ._mcp import MCPCallError, ProjectMCP
from core.tools.cloudflare_data import commit_production_outputs
from core.tools.r2_storage import download_public_file

from ._shared import (
    PROJECT_ROOT,
    qwen,
    qwen_vision,
    resolve_publish_date,
    upload_diagnostic_files,
    upload_run_files,
    write_summary,
)


VOICES = {"en": "en-US-AriaNeural", "zh": "zh-CN-XiaoxiaoNeural", "ko": "ko-KR-SunHiNeural"}
SUBJECT_GENERATION_MAX_ATTEMPTS = 3


def _choose_topic(recent_topics: list[str], requested_topic: str) -> str:
    recent = {str(item).strip().casefold() for item in recent_topics if str(item).strip()}
    if requested_topic.strip():
        topic = requested_topic.strip()
        if not re.fullmatch(r"[A-Za-z]+", topic):
            raise ValueError("语言学习 TOPIC 必须是一个不含空格的英文单词")
        if topic.casefold() in recent:
            raise ValueError(f"语言学习 TOPIC 最近 30 天已经发布：{topic}")
        return topic
    for _ in range(3):
        topic = str(qwen(
            "你是语言学习短视频选题编辑，只返回一个不含空格的英文单词，不加说明。",
            "选择一个能扩展出10个初学者生活常用词的英文类别词。"
            f"不得与最近30天主题重复：{json.dumps(recent_topics, ensure_ascii=False)}",
            max_tokens=30,
        )["text"]).strip().strip("“”\"'")
        if re.fullmatch(r"[A-Za-z]+", topic) and topic.casefold() not in recent:
            return topic
    raise ValueError("千问连续三次未返回单个英文单词 TOPIC")


def _delivery_config(topic: str, modes: list[str]) -> dict:
    """只生成后续发布所需文案元数据，不执行发布。"""
    result = {}
    if "en-zh" in modes:
        result["en-zh"] = {
            "account_group": "中文",
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
    """第一段：选题、创建生产目录并生成通过校验的双语词表。"""
    learning_modes = modes or ["en-zh", "en-ko"]
    publish_date = resolve_publish_date(publish_date)
    async with ProjectMCP("core.mcp.language_learning", PROJECT_ROOT) as mcp:
        topics = await mcp.call("language_learning_get_topics")
        topic = _choose_topic(topics.get("recent_topics") or [], requested_topic)
        occupied = await mcp.call(
            "language_learning_occupy_topic",
            {"topic": topic, "learning_modes": learning_modes, "publish_date": publish_date},
        )
        run_id = occupied["run_id"]
        prompt = await mcp.call(
            "language_learning_build_vocabulary_prompt",
            {"topic": topic, "learning_modes": learning_modes},
        )
        last_error = None
        for _ in range(3):
            response_text = qwen(
                "你是语言学习词表编辑。只输出用户规定的纯文本表格；第一行必须是“英文主题｜单个英文单词 TOPIC”，禁止 Markdown、标题、解释或省略首行。",
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
        "publish_date": publish_date,
        "run_id": run_id,
        "words": words,
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
    prompt = await mcp.call("language_learning_get_visual_validation_prompt")
    user_prompt = str(prompt["user_prompt"])
    if feedback:
        user_prompt += "\n\n上一次检查或抠图的问题如下。请重新观察原图并给出更保守、更准确的完整十框：\n- " + "\n- ".join(feedback)
    return qwen_vision(subject_sheet_path, str(prompt["system_prompt"]), user_prompt)


def _inspect_cutout(path: str, index: int, prompt: dict) -> dict:
    result = qwen_vision(
        path,
        str(prompt["system_prompt"]),
        str(prompt["user_prompt"]),
    )
    valid = result.get("valid")
    if not isinstance(valid, bool):
        raise RuntimeError(f"千问没有正确判断第 {index} 张抠图")
    failure_kind = str(result.get("failure_kind") or "").strip().casefold()
    if not valid and failure_kind not in {"crop", "source", "background_edge"}:
        failure_kind = "crop"
    return {
        "index": index,
        "valid": valid,
        "failure_kind": "" if valid else failure_kind,
        "issue": str(result.get("issue") or "").strip(),
    }


async def generate_cards(
    state_path: str | Path,
    diagnostics_dir: str | Path = "cache/github_actions/language-learning-diagnostics",
) -> dict:
    """第二段：生成主体图，经视觉验收和十张抠图检查后合成卡片。"""
    state = _read_state(state_path)
    topic = str(state["topic"])
    learning_modes = list(state["learning_modes"])
    run_id = str(state["run_id"])
    words = dict(state["words"])
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
        primary_words = words.get("en-zh") or words.get("en-ko")
        cutout_prompt = await mcp.call("language_learning_get_cutout_validation_prompt")
        generation_issues: list[str] = []
        for generation_attempt in range(1, SUBJECT_GENERATION_MAX_ATTEMPTS + 1):
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
                cutout_paths = [str(item) for item in validation.get("cutout_paths") or []]
                if len(cutout_paths) != 10:
                    visual_feedback = [f"Python 只输出了 {len(cutout_paths)} 张抠图，必须重新定位完整十个主体"]
                    continue
                reviews = [
                    _inspect_cutout(path, index, cutout_prompt)
                    for index, path in enumerate(cutout_paths, 1)
                ]
                review = await mcp.call(
                    "language_learning_review_cutouts",
                    {
                        "subject_sheet_path": submitted["subject_sheet_path"],
                        "reviews": reviews,
                        "run_id": run_id,
                    },
                )
                if review.get("approved") is True:
                    approved_validation = {**validation, "reviews": reviews, "visual_round": visual_round}
                    break
                visual_feedback = [
                    f"第 {item['index']} 个主体 [{item['failure_kind']}]：{item['issue'] or item['failure_kind']}"
                    for item in reviews
                    if not item["valid"]
                ]
                if review.get("action") == "regenerate":
                    generation_issues = visual_feedback
                    break
            if approved_validation is not None:
                break
            if not generation_issues:
                generation_issues = visual_feedback or ["视觉验收未通过"]
            source = Path(str(submitted["subject_sheet_path"])).resolve()
            failed_image = diagnostic_root / f"subject-sheet-attempt-{generation_attempt}{source.suffix.lower() or '.png'}"
            shutil.copy2(source, failed_image)
            diagnostic_payload["attempts"].append({
                "generation_attempt": generation_attempt,
                "file": failed_image.name,
                "issues": generation_issues,
            })
            diagnostic_payload["status"] = "retrying"
            _write_diagnostics(diagnostic_root, diagnostic_payload)
        else:
            diagnostic_payload["status"] = "failed"
            _write_diagnostics(diagnostic_root, diagnostic_payload)
            details = "；".join(generation_issues) or "没有返回具体视觉错误"
            raise RuntimeError(f"原始主题图连续 {SUBJECT_GENERATION_MAX_ATTEMPTS} 次未通过检查：{details}")
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
    source_reviews = list(source_validation.get("reviews") or [])
    publish_date = resolve_publish_date(publish_date)
    if not visual_layout or len(source_reviews) != 10:
        raise RuntimeError("旧 R2 清单缺少视觉框或十张抠图检查结果，不能安全原样重组")
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
        approved_reviews = [
            {"index": index, "valid": True, "failure_kind": "", "issue": "复用旧成片已通过的抠图"}
            for index in range(1, 11)
        ]
        review = await mcp.call(
            "language_learning_review_cutouts",
            {
                "subject_sheet_path": str(source_sheet_path),
                "reviews": approved_reviews,
                "run_id": run_id,
            },
        )
        if review.get("approved") is not True:
            raise RuntimeError("旧主题图的十张抠图未能重新批准")
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
            "reviews": approved_reviews,
            "source_run_id": source_id,
            "recomposed": True,
        },
        "card_dirs": card_dirs,
    }
    _write_state(state_path, state)
    return state


def upload_failed_subject_sheets(diagnostics_dir: str | Path) -> dict:
    """上传被视觉验收拒绝的主题图；没有失败图时跳过。"""
    root = Path(diagnostics_dir).resolve()
    metadata_path = root / "diagnostics.json"
    if not metadata_path.is_file():
        return {"status": "skipped", "reason": "本次任务没有主体图诊断记录"}
    metadata = _read_state(metadata_path)
    paths = [root / str(item["file"]) for item in metadata.get("attempts") or []]
    paths = [path for path in paths if path.is_file()]
    if not paths:
        return {"status": "skipped", "reason": "本次任务没有校验失败的主体图"}
    result = upload_diagnostic_files("language_learning", str(metadata["run_id"]), paths, metadata)
    write_summary(
        "语言学习失败主题图已上传 R2",
        [("主题", str(metadata["topic"])), ("失败图片数", str(len(paths))), ("保留时间", "1 天"), ("R2 诊断清单", str(result["manifest"]["url"]))],
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
        started = await mcp.call(
            "language_learning_start_create_videos",
            {
                "card_dirs": card_dirs,
                "words_by_mode": {mode: words[mode] for mode in learning_modes},
                "run_id": run_id,
                "voices": VOICES,
                "publish_config": _delivery_config(topic, learning_modes),
                "topic": topic,
                "language_pause": 0.3,
                "word_pause": 0.3,
                "production_source": "github_workflow",
            },
        )
        manifest = await mcp.poll("language_learning_poll_task", started["task_path"])
    manifest["subject_sheet_validation"] = dict(state["subject_sheet_validation"])
    destination = Path(handoff_dir).resolve()
    files_dir = destination / "files"
    files_dir.mkdir(parents=True, exist_ok=True)
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
        "subject_sheet_file": str(subject_sheet_target.relative_to(destination)),
        "video_files": video_files,
        "metadata_file": metadata_file,
        "manifest": manifest,
    }
    _write_state(destination / "handoff.json", handoff)
    return handoff


def upload_handoff(handoff_dir: str | Path) -> dict:
    """读取上一 Job 的交接文件，将成片与元数据上传 R2。"""
    destination = Path(handoff_dir).resolve()
    handoff = _read_state(destination / "handoff.json")
    video_paths = [destination / value for value in handoff["video_files"]]
    subject_sheet_path = destination / handoff["subject_sheet_file"]
    metadata_path = destination / handoff["metadata_file"] if handoff.get("metadata_file") else None
    manifest = dict(handoff["manifest"])
    manifest["output_dir"] = str(destination)
    paths = [subject_sheet_path, *video_paths]
    if metadata_path is not None:
        paths.append(metadata_path)
    remote = upload_run_files("language_learning", str(handoff["run_id"]), paths, manifest)
    uploaded_by_name = {
        str(item.get("source_name") or ""): str(item.get("url") or "")
        for item in remote.get("files") or []
    }
    publish_date = str(handoff.get("publish_date") or "").strip()
    if not publish_date:
        raw_date = str(handoff["run_id"]).removeprefix("run-")
        publish_date = f"{raw_date[:4]}-{raw_date[4:6]}-{raw_date[6:8]}"
    output_records = []
    for video in manifest.get("videos") or []:
        mode = str(video.get("learning_mode") or "").strip()
        for fallback_part, part in enumerate(video.get("video_parts") or [], 1):
            part_number = int(part.get("part") or fallback_part)
            source_name = Path(str(part.get("output_path") or "")).name
            r2_url = uploaded_by_name.get(source_name, "")
            if not r2_url:
                raise RuntimeError(f"R2 上传结果缺少成片地址：{source_name}")
            output_records.append({
                "production_id": f"github_workflow:language_learning:{handoff['run_id']}:{mode}:{part_number}",
                "run_id": str(handoff["run_id"]),
                "publish_date": publish_date,
                "business_line": "language_learning",
                "content_kind": mode,
                "content_part": part_number,
                "title": str(part.get("title") or "").strip(),
                "source": "github_workflow",
                "local_path": None,
                "r2_url": r2_url,
            })
    production_outputs = commit_production_outputs(output_records)
    subject_sheet_url = uploaded_by_name.get(subject_sheet_path.name, "")
    download_urls = {}
    for video in manifest.get("videos") or []:
        mode = str(video.get("learning_mode") or "").strip()
        urls = [
            uploaded_by_name.get(Path(value).name, "")
            for value in video.get("output_paths") or []
        ]
        urls = [url for url in urls if url]
        if urls:
            download_urls[mode] = urls[0]
    return {
        "manifest": manifest,
        "r2": remote,
        "production_outputs": production_outputs,
        "topic": str(handoff["topic"]),
        "subject_sheet_url": subject_sheet_url,
        "download_urls": download_urls,
    }


async def schedule_publication(
    manifest_url: str,
    run_id: str,
    *,
    targets: list[str] | None = None,
) -> dict:
    """通过语言学习 MCP 把尚未发布的平台排到计划发布日期北京时间 16:00。"""
    now = datetime.now(ZoneInfo("Asia/Shanghai"))
    try:
        publish_time = datetime.strptime(
            f"{str(run_id).removeprefix('run-')} 16:00",
            "%Y%m%d %H:%M",
        ).replace(tzinfo=ZoneInfo("Asia/Shanghai"))
    except ValueError as exc:
        raise RuntimeError("run_id 必须是包含有效计划发布日期的 run-YYYYMMDD") from exc
    if publish_time <= now:
        raise RuntimeError("计划发布日期的北京时间 16:00 已经过期，禁止预约到过去")
    publish_at = publish_time.isoformat()
    selected_targets = [
        str(item).strip().casefold()
        for item in (targets or ["youtube", "tiktok", "instagram", "facebook"])
        if str(item).strip()
    ]
    unknown = set(selected_targets) - {"youtube", "tiktok", "instagram", "facebook"}
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
    if result.get("success") is not True:
        raise RuntimeError(f"四平台排期存在失败：{json.dumps(result, ensure_ascii=False)}")
    completed_channels = {
        str(item.get("channel") or "").strip().casefold()
        for item in result.get("published") or []
        if item.get("success") is True
    }
    missing_channels = set(selected_targets) - completed_channels
    if missing_channels:
        raise RuntimeError(f"四平台排期返回不完整，缺少：{', '.join(sorted(missing_channels))}")
    return {"publish_at": publish_at, **result}
