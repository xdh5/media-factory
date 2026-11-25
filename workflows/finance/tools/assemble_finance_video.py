"""财经视频合成、稿件使用登记与 R2 交付。"""

from __future__ import annotations

from .toutiao_assets import prepare_toutiao_assets
from .youtube_short import produce_youtube_short
from pathlib import Path
from tools.paths import PROJECT_ROOT, PROJECT_STATIC_ROOT
from tools.generate_final_video._defaults import (
    DEFAULT_HOOK_SUBTITLE_POSITION,
    DEFAULT_HOOK_TITLE_DARK_OUTLINE,
    DEFAULT_HOOK_TITLE_FIRST_LINE_COLOR,
    DEFAULT_HOOK_TITLE_LIGHT_OUTLINE,
    DEFAULT_HOOK_TITLE_LINE_HEIGHT,
    DEFAULT_HOOK_TITLE_OTHER_LINE_COLOR,
    DEFAULT_HOOK_TITLE_POSITION,
    DEFAULT_HOOK_TITLE_SINGLE_COLOR,
    DEFAULT_HOOK_TITLE_STYLE,
    DEFAULT_SUBTITLE_POSITION,
    DEFAULT_SUBTITLE_STYLE,
)
from workflows.finance.errors.exceptions import WorkflowStepError
from workflows.finance.tools.video_effects import (
    _hook_title_lines_override,
    _with_display_text,
    _hook_layer,
    _render_first_shot_cached,
)
import json
import mimetypes
import shutil
from datetime import datetime, timezone
from workflows.finance.tools.cover import restore_cover_image
from tools.database.production_records import commit_production_outputs
from tools.r2_files import upload_file, upload_manifest
from tools.database.topic_history import record_topic_usage as commit_topic
from tools.generate_final_video import generate_final_video, safe_filename
from workflows.finance.parameters import (
    CONTENT_KIND,
    MCP_ID,
    TOPIC_DEDUPLICATION_DAYS,
    publish_date_from_run_id,
    VIDEO_SIZE,
)
from workflows.finance.tools.drafts import load_draft, save_source_usage
from workflows.finance.tools.storyboard import load_prepared_tts, parse_storyboard
from workflows.finance.tools.materials import _load_saved_storyboard, _apply_material, _write_attributions
from workflows.finance.infrastructure.scripts import mark_source_script_used


def _positive_int(value, field: str) -> int:
    if value is None:
        return 0
    if isinstance(value, bool) or not isinstance(value, int) or value < 0:
        raise WorkflowStepError(f"production_config.{field} 必须是非负整数")
    return value


def _production_config(config: dict) -> dict:
    bgm_path = str(config.get("bgm_path") or "").strip()
    intro = str(config.get("intro") or "").strip()
    if not bgm_path:
        raise WorkflowStepError("production_config.bgm_path 不能为空")
    if not intro:
        raise WorkflowStepError("production_config.intro 不能为空")
    stickers = config.get("shot_stickers")
    if not isinstance(stickers, list) or not stickers:
        raise WorkflowStepError("production_config.shot_stickers 必须是非空列表")
    subtitle_position = config.get("subtitle_position") or dict(DEFAULT_SUBTITLE_POSITION)
    subtitle_style = config.get("subtitle_style") or dict(DEFAULT_SUBTITLE_STYLE)
    subtitle_style = {**subtitle_style, "max_lines": 1, "word_wrap_after": 20,
                      "word_wrap_line_length": 20, "font_size": 76, "letter_spacing": 2,
                      "border_style": 3, "outline": 14, "outline_color": "&H46282828",
                      "shadow": 0}
    if not isinstance(subtitle_position, dict):
        raise WorkflowStepError("production_config.subtitle_position 必须是对象")
    if not isinstance(subtitle_style, dict):
        raise WorkflowStepError("production_config.subtitle_style 必须是对象")
    # 黄金钩子展示：钩子行数（第一个镜头的前 N 行）、钩子行位置、
    # 钩子期间居中显示的标题（文本/样式/位置均可配置）。
    # hook_lines 不传 = 按稿件黄金钩子自动识别行数；传 0 = 关闭钩子展示。
    raw_hook_lines = config.get("hook_lines")
    hook_lines = None if raw_hook_lines is None else _positive_int(raw_hook_lines, "hook_lines")
    hook_subtitle_position = config.get("hook_subtitle_position") or dict(DEFAULT_HOOK_SUBTITLE_POSITION)
    hook_title_style = config.get("hook_title_style") or dict(DEFAULT_HOOK_TITLE_STYLE)
    hook_title_position = config.get("hook_title_position") or dict(DEFAULT_HOOK_TITLE_POSITION)
    if not isinstance(hook_subtitle_position, dict):
        raise WorkflowStepError("production_config.hook_subtitle_position 必须是对象")
    if hook_title_style is not None and not isinstance(hook_title_style, dict):
        raise WorkflowStepError("production_config.hook_title_style 必须是对象")
    if not isinstance(hook_title_position, dict):
        raise WorkflowStepError("production_config.hook_title_position 必须是对象")
    # 标题配色：单行红字黑边；多行按标点断行，第一行字幕黄黑边，其余行红字白边。
    hook_title_single_color = str(config.get("hook_title_single_color") or DEFAULT_HOOK_TITLE_SINGLE_COLOR).strip()
    hook_title_first_line_color = str(config.get("hook_title_first_line_color") or DEFAULT_HOOK_TITLE_FIRST_LINE_COLOR).strip()
    hook_title_other_line_color = str(config.get("hook_title_other_line_color") or DEFAULT_HOOK_TITLE_OTHER_LINE_COLOR).strip()
    hook_title_dark_outline = str(config.get("hook_title_dark_outline") or DEFAULT_HOOK_TITLE_DARK_OUTLINE).strip()
    hook_title_light_outline = str(config.get("hook_title_light_outline") or DEFAULT_HOOK_TITLE_LIGHT_OUTLINE).strip()
    try:
        hook_title_line_height = float(
            config.get("hook_title_line_height") or DEFAULT_HOOK_TITLE_LINE_HEIGHT
        )
    except (TypeError, ValueError) as exc:
        raise WorkflowStepError("production_config.hook_title_line_height 必须是数字") from exc
    bgm_gain = config["bgm_gain"]
    try:
        bgm_gain = float(bgm_gain)
    except (TypeError, ValueError) as exc:
        raise WorkflowStepError("production_config.bgm_gain 必须是数字") from exc
    bgm = Path(bgm_path)
    if not bgm.is_absolute():
        resource_prefix = Path("tools/static")
        bgm = (PROJECT_STATIC_ROOT / bgm.relative_to(resource_prefix)
               if bgm.is_relative_to(resource_prefix) else PROJECT_ROOT / bgm)
    return {
        "bgm_path": bgm,
        "bgm_gain": bgm_gain,
        "bgm_credit": str(config.get("bgm_credit") or "").strip() or None,
        "intro": intro,
        "intro_sfx_path": Path(str(config["intro_sfx_path"])) if config.get("intro_sfx_path") else None,
        "shot_stickers": tuple(str(item) for item in stickers),
        "subtitle_position": subtitle_position,
        "subtitle_style": subtitle_style,
        "hook_lines": hook_lines,
        "hook_subtitle_position": hook_subtitle_position,
        "hook_title_text": str(config.get("hook_title_text") or "").strip(),
        # 优先使用宿主给出的标题换行，
        # 不传时只按句读断行，超宽保留完整词句并缩小字号。
        "hook_title_lines": _hook_title_lines_override(config.get("hook_title_lines")),
        "hook_title_style": hook_title_style,
        "hook_title_position": hook_title_position,
        "hook_title_single_color": hook_title_single_color,
        "hook_title_first_line_color": hook_title_first_line_color,
        "hook_title_other_line_color": hook_title_other_line_color,
        "hook_title_dark_outline": hook_title_dark_outline,
        "hook_title_light_outline": hook_title_light_outline,
        "hook_title_line_height": hook_title_line_height,
    }


def finish_finance_video(
    draft_path: str | Path,
    *,
    material_manifest_path: str | Path | None = None,
    production_config: dict,
    force_shot_ids: list[str] | None = None,
    production_source: str = "local_mcp",
    progress=None,
) -> dict:
    settings = _production_config(production_config)
    resolved_draft, draft = load_draft(draft_path, "财经稿件")
    if production_source not in {"local_mcp", "github_workflow"}:
        raise WorkflowStepError("production_source 必须是 local_mcp 或 github_workflow")
    record = {"id": draft["topic_record_id"], "topic": draft["topic"]}
    content_kind = str(draft.get("content_kind") or CONTENT_KIND)
    content_part = int(draft.get("content_part") or 1)
    run_id = str(draft["run_id"])
    article = str(draft["article"])
    metadata = {
        "title": str(draft["title"]),
        "short_title": str(draft["short_title"]),
        "micro_summary": str(draft.get("micro_summary") or ""),
        **{key: draft[key] for key in ("youtube_short_selection", "youtube_description", "youtube_hashtags")},
        "hashtags": list(draft["hashtags"]),
        "cover_lines": draft["cover_lines"],
        "cover_highlights": draft["cover_highlights"],
    }
    cache_root = Path(draft["cache_dir"]).resolve()
    output_root = Path(draft["output_dir"]).resolve()
    cache_root.mkdir(parents=True, exist_ok=True)
    output_root.mkdir(parents=True, exist_ok=True)

    tts = load_prepared_tts(cache_root)
    tts_path = tts["tts_path"]
    resolved_material_manifest = Path(material_manifest_path or "").resolve()
    if not resolved_material_manifest.is_file():
        raise WorkflowStepError(f"素材清单不存在：{resolved_material_manifest}")
    try:
        material_manifest = json.loads(resolved_material_manifest.read_text(encoding="utf-8"))
    except (OSError, json.JSONDecodeError) as exc:
        raise WorkflowStepError(f"读取素材清单失败：{resolved_material_manifest}。{exc}") from exc
    material_metadata = material_manifest["metadata"]
    storyboard_output = _load_saved_storyboard(material_metadata)
    shots = parse_storyboard(storyboard_output, tts["timeline"])
    stock_video, _ = _apply_material(
        material_manifest,
        shots,
        resolved_draft=resolved_draft,
        cache_root=cache_root,
        progress=progress,
    )
    material_strategy = str(material_metadata.get("material_strategy") or "")
    cover = restore_cover_image(draft["cover_images"]["landscape"], output_root / "cover.png")
    portrait_cover = restore_cover_image(draft["cover_images"]["portrait"], output_root / "cover-portrait.png")
    widescreen_cover = restore_cover_image(draft["cover_images"]["widescreen"], output_root / "cover-widescreen.png")

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
            "subtitle": "" if shot is shots[-1] else shot["subtitle"],
            "subtitle_lines": [] if shot is shots[-1] else shot.get("subtitle_lines") or [],
            "segment_path": shot.get("segment_path"),
            "image_path": shot.get("image_path"),
            "motion": shot.get("motion"),
            "duration": shot["duration"],
        }
        for shot in shots
    ]
    extra_ass_paths = _hook_layer(
        video_shots, settings, metadata, str(draft.get("source_hook") or ""), cache_root
    )
    try:
        final_result = generate_final_video(
            _with_display_text(video_shots),
            output_root / f"{safe_filename(metadata['title'])}.mp4",
            cache_root / "shot-cache",
            size=VIDEO_SIZE,
            tts_path=tts_path,
            bgm_path=settings["bgm_path"],
            bgm_start_seconds=0,
            bgm_gain=settings.get("bgm_gain"),
            stickers=list(settings["shot_stickers"]),
            force_shot_ids=[shot_id for shot_id in forced if shot_id != first_shot["id"]],
            opening_sfx=opening_sfx,
            subtitle_position=settings["subtitle_position"],
            subtitle_style=settings["subtitle_style"],
            secondary_subtitles={"enabled": False},
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
    if production_source in {"local_mcp", "github_workflow"}:
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
    source_hook_path = output_root / "source-hook.txt"
    title_path.write_text(metadata["title"] + "\n", encoding="utf-8")
    short_title_path.write_text(metadata["short_title"] + "\n", encoding="utf-8")
    publish_copy_path.write_text(publish_copy + "\n", encoding="utf-8")
    source_hook_path.write_text(str(draft.get("source_hook") or "").strip() + "\n", encoding="utf-8")
    attribution_comment_path = _write_attributions(material_manifest, settings, output_root)

    created_at = datetime.now(timezone.utc).isoformat(timespec="seconds").replace("+00:00", "Z")
    manifest = {
        "status": "produced",
        "line": MCP_ID,
        "content_kind": content_kind,
        "material_strategy": material_strategy,
        "intro_image_path": str(first_shot["image_path"]),
        "topic": record["topic"],
        "run_id": run_id,
        "content_part": content_part,
        "article": article,
        **metadata,
        "cover_path": cover["output_path"],
        "portrait_cover_path": portrait_cover["output_path"],
        "widescreen_cover_path": widescreen_cover["output_path"],
        "video_path": str(final_path),
        "cache_dir": str(cache_root),
        "output_dir": str(output_root),
        "title_path": str(title_path),
        "short_title_path": str(short_title_path),
        "publish_copy": publish_copy,
        "publish_copy_path": str(publish_copy_path),
        "source_hook": str(draft.get("source_hook") or "").strip(),
        "source_hook_path": str(source_hook_path),
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
    manifest.update(prepare_toutiao_assets(manifest))
    manifest.update(produce_youtube_short(manifest))
    manifest_path = cache_root / "manifest.json"
    manifest["manifest_path"] = str(manifest_path)
    manifest_path.write_text(json.dumps(manifest, ensure_ascii=False, indent=2), encoding="utf-8")
    return manifest


def _finish_video_and_commit_source_usage(
    draft_path: str,
    **kwargs,
) -> dict:
    """成片成功后才把占用中的数据库原稿标记为已使用。"""
    result = finish_finance_video(draft_path, **kwargs)
    _, draft = load_draft(draft_path, "财经稿件")
    if str(draft.get("source_database_status") or "") != "used":
        usage = mark_source_script_used(
            aweme_id=str(draft["source_aweme_id"]),
            workflow=MCP_ID,
            reservation_token=str(draft["source_reservation_token"]),
            run_id=str(draft["run_id"]),
            source_hook=str(draft["db_source_hook"]),
        )
        save_source_usage(draft_path, usage)
        result["source_usage"] = usage
    return result


def upload_finance_assets_to_r2(manifest_path: str | Path) -> dict:
    """上传财经发布资产，并把公网地址写回本地和远端清单。"""
    path = Path(manifest_path).resolve()
    if not path.is_file():
        raise WorkflowStepError(f"财经生产清单不存在：{path}")
    try:
        manifest = json.loads(path.read_text(encoding="utf-8"))
    except (OSError, json.JSONDecodeError) as exc:
        raise WorkflowStepError(f"读取财经生产清单失败：{path}。{exc}") from exc
    run_id = str(manifest.get("run_id") or "").strip()
    if not run_id:
        raise WorkflowStepError("财经生产清单缺少 run_id")
    content_part = int(manifest.get("content_part") or 1)
    # part 1 沿用历史 R2 路径；part 2 起加 -partN 后缀，避免同日多条互相覆盖。
    r2_dir = run_id if content_part <= 1 else f"{run_id}-part{content_part}"
    video_path = Path(str(manifest.get("video_path") or "")).resolve()
    cover_path = Path(str(manifest.get("cover_path") or "")).resolve()
    asset_fields = (
        "video_path",
        "cover_path",
        "portrait_cover_path",
        "widescreen_cover_path",
        "youtube_short_path",
        "youtube_description_path",
        "toutiao_article_path",
        "article_path",
        "micro_summary_path",
        "article_image_1_path",
        "article_image_2_path",
        "article_image_3_path",
        "title_path",
        "short_title_path",
        "publish_copy_path",
        "source_hook_path",
        "attribution_comment_path",
    )
    uploaded_assets: dict[str, dict] = {}
    for field in asset_fields:
        value = str(manifest.get(field) or "").strip()
        if not value:
            continue
        asset_path = Path(value).resolve()
        if not asset_path.is_file():
            raise WorkflowStepError(f"财经生产清单中的资产不存在：{field}={asset_path}")
        content_type = mimetypes.guess_type(asset_path.name)[0] or "application/octet-stream"
        uploaded_assets[field] = upload_file(
            asset_path,
            f"runs/{MCP_ID}/{r2_dir}/{asset_path.name}",
            content_type=content_type,
        )
    video = uploaded_assets["video_path"]
    cover = uploaded_assets["cover_path"]
    manifest["video_url"] = video["url"]
    manifest["video_r2_key"] = video["key"]
    manifest["cover_url"] = cover["url"]
    manifest["cover_r2_key"] = cover["key"]
    portrait_cover = uploaded_assets["portrait_cover_path"]
    manifest["portrait_cover_url"] = portrait_cover["url"]
    manifest["portrait_cover_r2_key"] = portrait_cover["key"]
    widescreen_cover = uploaded_assets["widescreen_cover_path"]
    manifest["widescreen_cover_url"] = widescreen_cover["url"]
    manifest["widescreen_cover_r2_key"] = widescreen_cover["key"]
    manifest["r2_uploaded"] = True
    # 成片记录固定写在 local_mcp 这一条上。GitHub 运行器销毁后本地路径会失效，发布端靠 r2_url 拉回。
    production_outputs = commit_production_outputs([{
        "production_id": f"local_mcp:{MCP_ID}:{run_id}:finance:{content_part}",
        "run_id": run_id,
        "publish_date": str(manifest.get("publish_date") or "").strip(),
        "business_line": MCP_ID,
        "content_kind": "finance",
        "content_part": content_part,
        "title": str(manifest.get("title") or "").strip(),
        "hashtags": " ".join(
            f"#{str(tag).strip().lstrip('#')}"
            for tag in manifest.get("hashtags") or []
            if str(tag).strip().lstrip("#")
        ),
        "source": "local_mcp",
        "local_path": str(video_path),
        "r2_url": video["url"],
        "r2_expires_at": None,
    }])
    manifest["production_outputs"] = production_outputs
    remote = upload_manifest(path, manifest, f"runs/{MCP_ID}/{r2_dir}/manifest.json")
    return {
        "manifest_path": str(path),
        "manifest_url": remote["url"],
        "video_url": video["url"],
        "cover_url": cover["url"],
        "portrait_cover_url": portrait_cover["url"],
        "widescreen_cover_url": widescreen_cover["url"],
        "uploaded": [*uploaded_assets.values(), remote],
        "production_outputs": production_outputs,
    }
