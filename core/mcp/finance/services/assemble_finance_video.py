"""财经成片合成与产物登记。"""

from __future__ import annotations

import json
from datetime import datetime, timezone
from pathlib import Path
from core.tools.generate_cover_image import CoverError, generate_cover_image
from core.tools.media_records import commit_production_outputs
from core.tools.topic_dedup import commit as commit_topic
from core.tools.generate_final_video import generate_final_video, safe_filename
from core.tools.generate_shot import intro_bgm_start_seconds
from ..config.settings import CONTENT_KIND, MATERIAL_STOCK_VIDEO, MCP_ID, TOPIC_DEDUPLICATION_DAYS, publish_date_from_run_id, VIDEO_SIZE
from ..errors import WorkflowStepError
from .save_draft import load_draft
from .storyboard import load_prepared_tts, parse_storyboard
from .video_materials import _load_saved_storyboard, _apply_material, _write_attributions
from .production_config import _production_config
from .video_layers import _with_display_text, _hook_layer, _chapter_layer
from .video_opening import _render_first_shot_cached


def finish_finance_video(
    draft_path: str | Path,
    *,
    material_manifest_path: str | Path | None = None,
    production_config: dict,
    intro_image_path: str | Path | None = None,
    storyboard_text: str | None = None,
    force_shot_ids: list[str] | None = None,
    production_source: str = "local_mcp",
    allow_auto_emphasis: bool = False,
    image_manifest_path: str | Path | None = None,
    progress=None,
) -> dict:
    settings = _production_config(production_config)
    resolved_draft, draft = load_draft(draft_path, "财经稿件")
    required_draft_fields = {
        "topic", "run_id", "topic_record_id", "article", "title", "short_title",
        "hashtags", "cache_dir", "output_dir",
    }
    missing_fields = sorted(required_draft_fields.difference(draft))
    if missing_fields:
        raise WorkflowStepError(
            f"财经稿件缺少字段：{missing_fields}",
            {"draft_path": str(resolved_draft)},
        )
    if production_source not in {"local_mcp", "github_workflow"}:
        raise WorkflowStepError("production_source 必须是 local_mcp 或 github_workflow")
    emphasis_settings = settings.get("emphasis_lines") or {}
    if (
        production_source == "local_mcp"
        and not allow_auto_emphasis
        and emphasis_settings.get("enabled", True)
        and emphasis_settings.get("groups") is None
    ):
        raise WorkflowStepError(
            "交互式 Finance 成片必须由宿主 Agent 在 production_config.emphasis_lines.groups "
            "传入重点句、语义断行和逐行标红词；MCP 禁止自行调用文本模型"
        )
    record = {"id": draft["topic_record_id"], "topic": draft["topic"]}
    content_kind = str(draft.get("content_kind") or CONTENT_KIND)
    content_part = int(draft.get("content_part") or 1)
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
    resolved_material_manifest = Path(material_manifest_path or image_manifest_path or "").resolve()
    if not resolved_material_manifest.is_file():
        raise WorkflowStepError(f"素材清单不存在：{resolved_material_manifest}")
    try:
        material_manifest = json.loads(resolved_material_manifest.read_text(encoding="utf-8"))
    except (OSError, json.JSONDecodeError) as exc:
        raise WorkflowStepError(f"读取素材清单失败：{resolved_material_manifest}。{exc}") from exc
    material_metadata = material_manifest.get("metadata")
    if not isinstance(material_metadata, dict):
        raise WorkflowStepError("素材清单缺少 metadata")
    storyboard_output = _load_saved_storyboard(material_metadata, cache_root, storyboard_text)
    shots = parse_storyboard(storyboard_output, tts["timeline"])
    stock_video, cover_sources = _apply_material(
        material_manifest,
        shots,
        resolved_draft=resolved_draft,
        intro_image_path=intro_image_path,
        cache_root=cache_root,
        progress=progress,
    )
    material_strategy = str(material_metadata.get("material_strategy") or "")
    if stock_video:
        material_strategy = MATERIAL_STOCK_VIDEO
    elif not material_strategy:
        image_config = material_manifest.get("image_config")
        if isinstance(image_config, dict):
            material_strategy = str(image_config.get("source") or "").strip()
    try:
        # 实拍视频策略从本期下载的视频帧随机取封面底图；保留原有标题排版、重点词和描边。
        cover_image_sources = cover_sources
        cover = generate_cover_image(
            cover_image_sources,
            metadata["title"],
            cache_root / "cover.png",
            size=VIDEO_SIZE,
            lines=metadata["cover_lines"],
            highlighted_words=metadata["cover_highlights"],
        )
    except CoverError as exc:
        raise WorkflowStepError(exc.message, exc.details) from exc

    forced = set(force_shot_ids or [])
    unknown_forced = forced.difference(shot["id"] for shot in shots)
    if unknown_forced:
        raise WorkflowStepError(f"要重做的镜头不存在：{sorted(unknown_forced)}")
    segment_dir = cache_root / "segments"
    segment_dir.mkdir(parents=True, exist_ok=True)
    first_shot = shots[0]
    first_segment = segment_dir / f"{first_shot['id']}.mp4"
    first_shot["cache_hit"], opening_sfx = _render_first_shot_cached(
        settings["intro"],
        settings["intro_sfx_path"],
        shots,
        first_shot,
        first_segment,
        force=first_shot["id"] in forced,
    )
    first_shot["segment_path"] = str(first_segment)
    video_shots = [
        {
            "id": shot["id"],
            "subtitle": shot["subtitle"],
            "subtitle_lines": shot.get("subtitle_lines") or [],
            **(
                {"segment_path": shot["segment_path"]}
                if shot.get("segment_path")
                else {
                    "image_path": shot["image_path"],
                    "duration": shot["duration"],
                    "motion": shot["motion"],
                }
            ),
        }
        for shot in shots
    ]
    extra_ass_paths = _hook_layer(
        video_shots, settings, metadata, str(draft.get("source_hook") or ""), cache_root
    )
    extra_ass_paths += _chapter_layer(shots, settings, cache_root, progress=progress)
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
            bgm_start_seconds=intro_bgm_start_seconds(
                settings["intro"],
                first_shot_duration=float(first_shot["duration"]),
            ),
            bgm_gain=settings.get("bgm_gain"),
            stickers=list(settings["shot_stickers"]),
            force_shot_ids=[shot_id for shot_id in forced if shot_id != first_shot["id"]],
            opening_sfx=opening_sfx,
            subtitle_position=settings["subtitle_position"],
            subtitle_style=settings["subtitle_style"],
            secondary_subtitles=settings["secondary_subtitles"],
            emphasis_lines=settings["emphasis_lines"],
            extra_ass_paths=extra_ass_paths,
            normalize_composed=stock_video and not material_manifest.get("normalized_cfr"),
            progress=progress,
        )
    except Exception as extra:
        raise WorkflowStepError(f"财经成片失败：{extra}") from extra
    final_path = Path(final_result["output_path"])
    publish_date = publish_date_from_run_id(run_id)
    topic_commit = commit_topic(
        MCP_ID, record["topic"], f"{MCP_ID}:{run_id}:{content_part}",
        days=TOPIC_DEDUPLICATION_DAYS,
    )
    production_outputs = None
    if production_source == "local_mcp":
        production_outputs = commit_production_outputs([{
            "production_id": f"local_mcp:finance:{run_id}:{content_kind}:{content_part}",
            "run_id": run_id,
            "publish_date": publish_date,
            "business_line": "finance",
            "content_kind": content_kind,
            "content_part": content_part,
            "title": metadata["title"],
            "hashtags": " ".join(f"#{str(tag).lstrip('#')}" for tag in metadata["hashtags"]),
            "source": "local_mcp",
            "local_path": str(final_path),
            "r2_url": None,
            "r2_expires_at": None,
        }])

    publish_copy = metadata["short_title"] + " " + " ".join(
        f"#{tag.lstrip('#')}" for tag in metadata["hashtags"]
    )
    title_path = output_root / "title.txt"
    short_title_path = output_root / "short-title.txt"
    publish_copy_path = output_root / "publish-copy.txt"
    title_path.write_text(metadata["title"] + "\n", encoding="utf-8")
    short_title_path.write_text(metadata["short_title"] + "\n", encoding="utf-8")
    publish_copy_path.write_text(publish_copy + "\n", encoding="utf-8")
    attribution_comment_path = _write_attributions(material_manifest, settings, output_root)

    created_at = datetime.now(timezone.utc).isoformat(timespec="seconds").replace("+00:00", "Z")
    manifest = {
        "status": "produced",
        "line": MCP_ID,
        "content_kind": content_kind,
        "material_strategy": material_strategy,
        "intro_image_path": (
            str(first_shot["image_path"]) if stock_video else None
        ),
        "topic": record["topic"],
        "run_id": run_id,
        "content_part": content_part,
        "article": article,
        **metadata,
        "cover_path": cover["output_path"],
        "video_path": str(final_path),
        "cache_dir": str(cache_root),
        "output_dir": str(output_root),
        "title_path": str(title_path),
        "short_title_path": str(short_title_path),
        "publish_copy": publish_copy,
        "publish_copy_path": str(publish_copy_path),
        "attribution_comment_path": attribution_comment_path,
        "stock_video_attributions": list(material_manifest.get("attributions") or []),
        "performance": {"materials_seconds": material_manifest.get("elapsed_seconds"),
                        "material_shots": material_manifest.get("timings"),
                        "final_cache_hit": final_result.get("cache_hit"),
                        "final_timings": final_result.get("timings")},
        "created_at": created_at,
        "publish_date": publish_date,
        "production_source": production_source,
        "production_outputs": production_outputs,
        "topic_record_id": record["id"],
        "topic_commit": topic_commit,
        "shots": shots,
    }
    manifest_path = cache_root / "manifest.json"
    manifest["manifest_path"] = str(manifest_path)
    manifest_path.write_text(json.dumps(manifest, ensure_ascii=False, indent=2), encoding="utf-8")
    return manifest

