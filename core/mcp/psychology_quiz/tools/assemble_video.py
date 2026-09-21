"""心灵鸡汤成片：封面与最终合成。"""

from __future__ import annotations

import hashlib
import json
from datetime import datetime, timezone
from pathlib import Path

from core.tools.generate_cover_image import CoverError, generate_cover_image
from core.tools.cloudflare_data import commit_production_outputs, commit_scenario_quiz_question
from core.tools.generate_final_video import generate_final_video, safe_filename
from core.tools.generate_shot import (
    SFX_ALERT_GAIN,
    SFX_ALERT_PATH,
    SFX_ALERT_SECONDS,
    SFX_SHUTTER_GAIN,
    SFX_SHUTTER_PATH,
    SFX_SHUTTER_SECONDS,
    SHUTTER_START_SECONDS,
    ShotToolError,
    generate_shot_from_intro,
    intro_bgm_start_seconds,
)
from core.tools.quiz_timeline import generate_quiz_timeline_ass

from .._constants import (
    MATRIXMEDIA_AI_CREATIVE_STATEMENT,
    MCP_ID,
    STORYBOARD_TEXT_FILE_NAME,
    TOPIC_DEDUPLICATION_DAYS,
    publish_date_from_run_id,
    VIDEO_SIZE,
)
from .._errors import WorkflowStepError
from .narration import display_subtitle_cue, display_subtitle_text
from .draft import load_draft
from .storyboard import load_prepared_tts, parse_storyboard


def _production_config(config: dict) -> dict:
    bgm_path = str(config.get("bgm_path") or "").strip()
    intro = str(config.get("intro") or "").strip()
    account_group = str(config.get("matrixmedia_account_group") or "").strip()
    if not bgm_path:
        raise WorkflowStepError("production_config.bgm_path 不能为空")
    if not intro:
        raise WorkflowStepError("production_config.intro 不能为空")
    if not account_group:
        raise WorkflowStepError("production_config.matrixmedia_account_group 不能为空")
    try:
        cover_frame_seconds = float(config.get("cover_frame_seconds"))
    except (TypeError, ValueError) as exc:
        raise WorkflowStepError("production_config.cover_frame_seconds 必须是数字") from exc
    stickers = config.get("shot_stickers")
    if not isinstance(stickers, list):
        raise WorkflowStepError("production_config.shot_stickers 必须是列表")
    subtitle_style = config.get("subtitle_style")
    subtitle_position = config.get("subtitle_position") or {
        "alignment": 5,
        "margin_vertical_ratio": 0.5,
    }
    if subtitle_style is not None and not isinstance(subtitle_style, dict):
        raise WorkflowStepError("production_config.subtitle_style 必须是对象")
    if subtitle_position is not None and not isinstance(subtitle_position, dict):
        raise WorkflowStepError("production_config.subtitle_position 必须是对象")
    timeline_position = str(config.get("quiz_timeline_position") or "bottom").strip().lower()
    if timeline_position not in {"bottom", "top"}:
        raise WorkflowStepError("production_config.quiz_timeline_position 只能是 bottom 或 top")
    chapter_titles = config.get("quiz_chapter_titles") or [
        "情境引入",
        "A/B/C/D怎么选",
        "选好了吗",
        "四种答案解析",
        "评论区见",
    ]
    if not isinstance(chapter_titles, list) or len(chapter_titles) != 5:
        raise WorkflowStepError("production_config.quiz_chapter_titles 必须包含五个章节标题")
    chapter_titles = [str(item).strip() for item in chapter_titles]
    if any(not item for item in chapter_titles):
        raise WorkflowStepError("production_config.quiz_chapter_titles 不能包含空标题")
    return {
        "bgm_path": Path(bgm_path),
        "intro": intro,
        "cover_frame_seconds": cover_frame_seconds,
        "shot_stickers": tuple(str(item) for item in stickers),
        "matrixmedia_account_group": account_group,
        "subtitle_style": subtitle_style,
        "subtitle_position": subtitle_position,
        "quiz_timeline_position": timeline_position,
        "quiz_chapter_titles": chapter_titles,
    }


def _with_display_text(shots: list[dict]) -> list[dict]:
    prepared: list[dict] = []
    for shot in shots:
        item = dict(shot)
        if item.get("subtitle") is not None:
            item["subtitle"] = display_subtitle_text(str(item.get("subtitle") or ""))
        lines = item.get("subtitle_lines")
        if isinstance(lines, list):
            cleaned = []
            for line in lines:
                if not isinstance(line, dict):
                    continue
                row = dict(line)
                try:
                    cue = display_subtitle_cue(str(row.get("text") or ""))
                except ValueError as extra:
                    raise WorkflowStepError(f"镜头 {item.get('id')} 字幕重点标记无效：{extra}") from extra
                row["text"] = cue
                cleaned.append(row)
            item["subtitle_lines"] = cleaned
        prepared.append(item)
    return prepared


def _opening_sfx() -> list[dict]:
    items = []
    if SFX_ALERT_PATH.is_file():
        items.append({"path": str(SFX_ALERT_PATH), "start": 0.0, "duration": SFX_ALERT_SECONDS, "gain": SFX_ALERT_GAIN})
    if SFX_SHUTTER_PATH.is_file():
        items.append({"path": str(SFX_SHUTTER_PATH), "start": SHUTTER_START_SECONDS, "duration": SFX_SHUTTER_SECONDS, "gain": SFX_SHUTTER_GAIN})
    return items


def _render_intro(image_path: Path, shot: dict, segment_path: Path, intro: str) -> list[dict]:
    if not image_path.is_file():
        raise WorkflowStepError(f"片头写实图不存在：{image_path}")
    try:
        generate_shot_from_intro(
            intro,
            segment_path,
            duration=shot["duration"],
            image_path=image_path,
            motion=shot["motion"],
        )
    except ShotToolError as exc:
        raise WorkflowStepError(exc.message, exc.details) from exc
    return _opening_sfx() if intro == "slide_in_shutter" else []


def _mark_scenario_quiz_used(draft: dict) -> dict | None:
    """情境测试成片成功后，把题库记录从占用更新为已使用。"""
    if str(draft.get("content_kind") or "") != "scenario_quiz":
        return None
    quiz = draft.get("quiz")
    if not isinstance(quiz, dict):
        raise WorkflowStepError("情境测试稿件缺少 quiz，无法更新题库状态")
    options = quiz.get("options")
    results = quiz.get("results")
    if not isinstance(options, dict) or not isinstance(results, dict):
        raise WorkflowStepError("情境测试稿件缺少完整选项或结果，无法更新题库状态")
    return commit_scenario_quiz_question({
        "run_id": draft["run_id"],
        "topic_record_id": draft["topic_record_id"],
        "topic": draft["topic"],
        "category": quiz["category"],
        "scene_title": quiz["scene_title"],
        "scenario": quiz["scenario"],
        "option_a": options["a"],
        "option_b": options["b"],
        "option_c": options["c"],
        "option_d": options["d"],
        "result_a": results["a"],
        "result_b": results["b"],
        "result_c": results["c"],
        "result_d": results["d"],
        "image_keywords": quiz["video_keywords"],
        "status": "used",
        "publish_date": draft["publish_date"],
    })


def _storyboard_hash(value: str) -> str:
    return hashlib.sha256(value.encode("utf-8")).hexdigest()


def _load_saved_storyboard(
    image_metadata: dict,
    cache_root: Path,
    storyboard_text: str | None,
) -> str:
    saved = str(image_metadata.get("storyboard_text") or "").strip()
    saved_path = Path(str(image_metadata.get("storyboard_path") or "")).resolve()
    if not saved and saved_path.is_file():
        saved = saved_path.read_text(encoding="utf-8").strip()
    fallback_path = cache_root / STORYBOARD_TEXT_FILE_NAME
    if not saved and fallback_path.is_file():
        saved = fallback_path.read_text(encoding="utf-8").strip()
    if saved:
        expected_hash = str(image_metadata.get("storyboard_sha256") or "").strip()
        if expected_hash and _storyboard_hash(saved) != expected_hash:
            raise WorkflowStepError(
                "已保存的分镜文本损坏，请重新调用 psychology_quiz_start_video_search",
                {"storyboard_sha256": expected_hash},
            )
        return saved
    fallback = str(storyboard_text or "").strip()
    if not fallback:
        raise WorkflowStepError(
            "视频素材清单里没有分镜文本。请重新调用 psychology_quiz_start_video_search"
        )
    expected_hash = str(image_metadata.get("storyboard_sha256") or "").strip()
    if expected_hash and _storyboard_hash(fallback) != expected_hash:
        raise WorkflowStepError(
            "传入的 storyboard_text 与搜索视频时不一致。请重新调用 psychology_quiz_start_video_search",
            {"storyboard_sha256": expected_hash, "received_sha256": _storyboard_hash(fallback)},
        )
    return fallback


def finish_psychology_quiz_video(
    draft_path: str | Path,
    *,
    video_manifest_path: str | Path,
    intro_image_path: str | Path,
    production_config: dict,
    storyboard_text: str | None = None,
    force_shot_ids: list[str] | None = None,
    production_source: str = "local_mcp",
    progress=None,
) -> dict:
    settings = _production_config(production_config)
    resolved_draft, draft = load_draft(draft_path, "心灵鸡汤稿件")
    required_draft_fields = {
        "topic", "run_id", "topic_record_id", "article", "title", "short_title",
        "hashtags", "cache_dir", "output_dir",
    }
    missing_fields = sorted(required_draft_fields.difference(draft))
    if missing_fields:
        raise WorkflowStepError(
            f"心灵鸡汤稿件缺少字段：{missing_fields}",
            {"draft_path": str(resolved_draft)},
        )
    if production_source not in {"local_mcp", "github_workflow"}:
        raise WorkflowStepError("production_source 必须是 local_mcp 或 github_workflow")
    record = {"id": draft["topic_record_id"], "topic": draft["topic"]}
    content_kind = str(draft.get("content_kind") or "scenario_quiz")
    run_id = str(draft["run_id"])
    article = str(draft["article"])
    metadata = {
        "title": str(draft["title"]),
        "short_title": str(draft["short_title"]),
        "hashtags": list(draft["hashtags"]),
        "cover_lines": list(draft.get("cover_lines") or [str(draft["title"])]),
        "cover_highlights": list(draft.get("cover_highlights") or [str(draft["title"])]),
    }
    cache_root = Path(draft["cache_dir"]).resolve()
    output_root = Path(draft["output_dir"]).resolve()
    cache_root.mkdir(parents=True, exist_ok=True)
    output_root.mkdir(parents=True, exist_ok=True)

    tts = load_prepared_tts(cache_root)
    tts_path = tts["tts_path"]
    resolved_video_manifest = Path(video_manifest_path).resolve()
    if not resolved_video_manifest.is_file():
        raise WorkflowStepError(f"视频素材清单不存在：{resolved_video_manifest}")
    try:
        video_manifest = json.loads(resolved_video_manifest.read_text(encoding="utf-8"))
    except (OSError, json.JSONDecodeError) as exc:
        raise WorkflowStepError(f"读取视频素材清单失败：{resolved_video_manifest}。{exc}") from exc
    video_metadata = video_manifest.get("metadata")
    if not isinstance(video_metadata, dict):
        raise WorkflowStepError("视频素材清单缺少 metadata")
    if Path(str(video_metadata.get("draft_path") or "")).resolve() != resolved_draft:
        raise WorkflowStepError("视频素材清单不属于当前稿件，请重新搜索视频")
    storyboard_output = _load_saved_storyboard(video_metadata, cache_root, storyboard_text)
    shots = parse_storyboard(storyboard_output, tts["timeline"])
    videos = video_manifest.get("videos")
    frames = video_manifest.get("frames")
    if len(shots) < 2:
        raise WorkflowStepError("分镜至少需要两个镜头：片头动画后必须有正文视频素材")
    expected_video_ids = {shot["id"] for shot in shots[1:]}
    if not isinstance(videos, dict) or set(videos) != expected_video_ids:
        raise WorkflowStepError(
            "视频素材清单没有完整覆盖所有镜头",
            {"expected_video_ids": sorted(expected_video_ids), "actual_video_ids": sorted(videos or {})},
        )
    if not isinstance(frames, dict) or set(frames) != expected_video_ids:
        raise WorkflowStepError("视频素材清单缺少完整封面帧")
    for video_id, video_path in videos.items():
        if not Path(str(video_path)).resolve().is_file():
            raise WorkflowStepError(f"视频素材不存在：{video_id} -> {video_path}")
    for shot in shots[1:]:
        shot["segment_path"] = str(Path(videos[shot["id"]]).resolve())
        shot["frame_path"] = str(Path(frames[shot["id"]]).resolve())
    resolved_intro_image = Path(intro_image_path).resolve()
    intro_segment = cache_root / "stock-videos" / "clips" / "shot-001-intro.mp4"
    opening_sfx = _render_intro(resolved_intro_image, shots[0], intro_segment, settings["intro"])
    shots[0]["segment_path"] = str(intro_segment)
    shots[0]["frame_path"] = str(resolved_intro_image)
    try:
        cover = generate_cover_image(
            [shot["frame_path"] for shot in shots],
            metadata["title"],
            cache_root / "cover.png",
            size=VIDEO_SIZE,
            lines=metadata["cover_lines"],
            highlighted_words=metadata["cover_highlights"],
        )
    except CoverError as exc:
        raise WorkflowStepError(exc.message, exc.details) from exc

    video_shots = [
        {
            "id": shot["id"],
            "segment_path": shot["segment_path"],
            "subtitle": shot["subtitle"],
            "subtitle_lines": shot.get("subtitle_lines") or [],
        }
        for shot in shots
    ]
    if len(shots) < 14:
        raise WorkflowStepError(
            "心灵鸡汤分镜不足14段，无法生成情境、选项、结果和结尾章节时间轴"
        )
    option_stages = []
    result_stages = []
    for label, shot_index in zip(("A", "B", "C", "D"), (4, 5, 6, 7)):
        stage = shots[shot_index]
        option_stages.append({"label": label, "start": stage["audio_start"], "end": stage["audio_end"]})
    for label, shot_index in zip(("A", "B", "C", "D"), (9, 10, 11, 12)):
        stage = shots[shot_index]
        result_stages.append({"label": label, "start": stage["audio_start"], "end": stage["audio_end"]})
    total_duration = float(tts.get("tts_duration") or sum(float(item["duration"]) for item in shots))
    chapter_boundaries = [
        0.0,
        float(shots[4]["audio_start"]),
        float(shots[8]["audio_start"]),
        float(shots[9]["audio_start"]),
        float(shots[13]["audio_start"]),
        total_duration,
    ]
    chapters = [
        {
            "title": title,
            "start": chapter_boundaries[index],
            "end": chapter_boundaries[index + 1],
        }
        for index, title in enumerate(settings["quiz_chapter_titles"])
    ]
    quiz_timeline = generate_quiz_timeline_ass(
        cache_root / "quiz-timeline.ass",
        total_duration,
        option_stages,
        result_stages,
        chapters,
        position=settings["quiz_timeline_position"],
    )
    try:
        final_result = generate_final_video(
            _with_display_text(video_shots),
            output_root / f"{safe_filename(metadata['title'])}.mp4",
            cache_root / "shot-cache",
            size=VIDEO_SIZE,
            tts_path=tts_path,
            cover_path=cover["output_path"],
            cover_duration=settings["cover_frame_seconds"],
            bgm_path=settings["bgm_path"],
            stickers=list(settings["shot_stickers"]),
            force_shot_ids=force_shot_ids,
            opening_sfx=opening_sfx,
            bgm_start_seconds=intro_bgm_start_seconds(
                settings["intro"],
                first_shot_duration=shots[0]["duration"],
            ),
            subtitle_style=settings["subtitle_style"],
            subtitle_position=settings["subtitle_position"],
            extra_ass_paths=[quiz_timeline["output_path"]],
            normalize_composed=True,
            progress=progress,
        )
    except Exception as extra:
        raise WorkflowStepError(f"心灵鸡汤成片失败：{extra}") from extra
    final_path = Path(final_result["output_path"])
    publish_date = publish_date_from_run_id(run_id)
    production_outputs = None
    if production_source == "local_mcp":
        production_outputs = commit_production_outputs([{
            "production_id": f"local_mcp:psychology_quiz:{run_id}:{content_kind}:1",
            "run_id": run_id,
            "publish_date": publish_date,
            "business_line": "psychology_quiz",
            "content_kind": content_kind,
            "content_part": 1,
            "title": metadata["title"],
            "hashtags": " ".join(f"#{str(tag).lstrip('#')}" for tag in metadata["hashtags"]),
            "source": "local_mcp",
            "local_path": str(final_path),
            "r2_url": None,
            "r2_expires_at": None,
        }])
    scenario_quiz_record = _mark_scenario_quiz_used(draft)

    publish_copy = metadata["short_title"] + " " + " ".join(
        f"#{tag.lstrip('#')}" for tag in metadata["hashtags"]
    )
    title_path = output_root / "title.txt"
    short_title_path = output_root / "short-title.txt"
    publish_copy_path = output_root / "publish-copy.txt"
    title_path.write_text(metadata["title"] + "\n", encoding="utf-8")
    short_title_path.write_text(metadata["short_title"] + "\n", encoding="utf-8")
    publish_copy_path.write_text(publish_copy + "\n", encoding="utf-8")
    attributions = list(video_manifest.get("attributions") or [])
    seen_sources: set[tuple[str, str]] = set()
    attribution_lines: list[str] = []
    for item in attributions:
        if not isinstance(item, dict):
            continue
        source_key = (str(item.get("provider") or ""), str(item.get("source_id") or ""))
        if source_key in seen_sources:
            continue
        seen_sources.add(source_key)
        label = str(item.get("attribution") or item.get("provider") or "素材来源").strip()
        url = str(item.get("attribution_url") or item.get("page_url") or "").strip()
        attribution_lines.append(f"{label} {url}".strip())
    attribution_comment_path = output_root / "attribution-comment.txt"
    attribution_comment_path.write_text("\n".join(attribution_lines) + "\n", encoding="utf-8")

    created_at = datetime.now(timezone.utc).isoformat(timespec="seconds").replace("+00:00", "Z")
    manifest = {
        "status": "awaiting_publish_confirmation",
        "confirmation_required": "publish",
        "line": MCP_ID,
        "content_kind": content_kind,
        "topic": record["topic"],
        "run_id": run_id,
        "article": article,
        **metadata,
        "cover_path": cover["output_path"],
        "intro_image_path": str(resolved_intro_image),
        "video_path": str(final_path),
        "cache_dir": str(cache_root),
        "output_dir": str(output_root),
        "title_path": str(title_path),
        "short_title_path": str(short_title_path),
        "publish_bt2": metadata["short_title"],
        "publish_copy": publish_copy,
        "publish_copy_path": str(publish_copy_path),
        "attribution_comment_path": str(attribution_comment_path),
        "matrixmedia_account_group": settings["matrixmedia_account_group"],
        "creativeStatement": MATRIXMEDIA_AI_CREATIVE_STATEMENT,
        "created_at": created_at,
        "publish_date": publish_date,
        "production_source": production_source,
        "production_outputs": production_outputs,
        "scenario_quiz_record": scenario_quiz_record,
        "stock_video_attributions": attributions,
        "topic_record_id": record["id"],
        "database_commit": {
            "workflow": MCP_ID,
            "publication_id": f"{MCP_ID}:{run_id}",
            "run_id": run_id,
            "topic": record["topic"],
            "days": TOPIC_DEDUPLICATION_DAYS,
            "entries": [],
        },
        "shots": shots,
    }
    manifest_path = cache_root / "manifest.json"
    manifest["manifest_path"] = str(manifest_path)
    manifest_path.write_text(json.dumps(manifest, ensure_ascii=False, indent=2), encoding="utf-8")
    return manifest
