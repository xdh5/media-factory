"""财经成片参数校验。"""

from __future__ import annotations

from pathlib import Path
from core.tools.generate_final_video._defaults import DEFAULT_CHAPTER_TIMELINE, DEFAULT_HOOK_SUBTITLE_POSITION, DEFAULT_HOOK_TITLE_DARK_OUTLINE, DEFAULT_HOOK_TITLE_FIRST_LINE_COLOR, DEFAULT_HOOK_TITLE_LIGHT_OUTLINE, DEFAULT_HOOK_TITLE_LINE_HEIGHT, DEFAULT_HOOK_TITLE_OTHER_LINE_COLOR, DEFAULT_HOOK_TITLE_POSITION, DEFAULT_HOOK_TITLE_SINGLE_COLOR, DEFAULT_HOOK_TITLE_STYLE, DEFAULT_BGM_GAIN, DEFAULT_EMPHASIS_LINES, DEFAULT_SECONDARY_SUBTITLES, DEFAULT_SUBTITLE_POSITION, DEFAULT_SUBTITLE_STYLE
from ..errors import WorkflowStepError
from .video_layers import _hook_title_lines_override


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
    try:
        cover_frame_seconds = float(config.get("cover_frame_seconds"))
    except (TypeError, ValueError) as exc:
        raise WorkflowStepError("production_config.cover_frame_seconds 必须是数字") from exc
    stickers = config.get("shot_stickers")
    if not isinstance(stickers, list) or not stickers:
        raise WorkflowStepError("production_config.shot_stickers 必须是非空列表")
    subtitle_position = config.get("subtitle_position") or dict(DEFAULT_SUBTITLE_POSITION)
    subtitle_style = config.get("subtitle_style") or dict(DEFAULT_SUBTITLE_STYLE)
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
    bgm_gain = config.get("bgm_gain")
    if bgm_gain is None:
        # 2026-09-23 起财经线统一默认（0.84 基础上 -20%），两个生产入口保持一致。
        bgm_gain = DEFAULT_BGM_GAIN
    try:
        bgm_gain = float(bgm_gain)
    except (TypeError, ValueError) as exc:
        raise WorkflowStepError("production_config.bgm_gain 必须是数字") from exc
    # 中文下方的英文翻译字幕层：None = 默认开启（字号=中文字号×0.4，白字黑边）。
    secondary_subtitles = config.get("secondary_subtitles")
    if secondary_subtitles is None:
        secondary_settings = dict(DEFAULT_SECONDARY_SUBTITLES)
    elif isinstance(secondary_subtitles, dict):
        secondary_settings = {
            **DEFAULT_SECONDARY_SUBTITLES,
            **secondary_subtitles,
            "style": {
                **DEFAULT_SECONDARY_SUBTITLES["style"],
                **(secondary_subtitles.get("style") or {}),
            },
            "position": {
                **DEFAULT_SECONDARY_SUBTITLES["position"],
                **(secondary_subtitles.get("position") or {}),
            },
        }
        unknown = set(secondary_subtitles) - {"enabled", "font_size_ratio", "style", "position"}
        if unknown:
            raise WorkflowStepError(
                f"production_config.secondary_subtitles 含未知字段：{sorted(unknown)}"
            )
    else:
        raise WorkflowStepError("production_config.secondary_subtitles 必须是对象")
    # 章节时间轴条：None = 用默认（贴下方、8 段、AI 标题）；enabled=False 关闭。
    chapter_timeline = config.get("chapter_timeline")
    if chapter_timeline is not None and not isinstance(chapter_timeline, dict):
        raise WorkflowStepError("production_config.chapter_timeline 必须是对象")
    if chapter_timeline is None:
        chapter_settings = dict(DEFAULT_CHAPTER_TIMELINE)
    else:
        chapter_settings = {**DEFAULT_CHAPTER_TIMELINE, **chapter_timeline}
        unknown = set(chapter_timeline) - {
            "enabled", "position", "segment_count", "ai_titles", "font_size",
            "bar_height", "margin_horizontal", "margin_vertical_ratio",
            "track_color", "track_opacity", "title_color", "active_color",
            "progress_color", "progress_opacity", "separator_color",
            "separator_opacity", "separator_width", "font",
        }
        if unknown:
            raise WorkflowStepError(
                f"production_config.chapter_timeline 含未知字段：{sorted(unknown)}"
            )
    chapter_settings["enabled"] = bool(chapter_settings.get("enabled", True))
    chapter_settings["ai_titles"] = bool(chapter_settings.get("ai_titles", True))
    chapter_settings["position"] = str(chapter_settings.get("position") or "bottom").strip().lower()
    if chapter_settings["position"] not in ("top", "bottom"):
        raise WorkflowStepError("production_config.chapter_timeline.position 必须是 top 或 bottom")
    try:
        chapter_settings["segment_count"] = int(chapter_settings.get("segment_count") or 8)
    except (TypeError, ValueError) as exc:
        raise WorkflowStepError("production_config.chapter_timeline.segment_count 必须是整数") from exc
    if not 2 <= chapter_settings["segment_count"] <= 12:
        raise WorkflowStepError("production_config.chapter_timeline.segment_count 必须在 2~12 之间")
    # 重点句大字层：None = 默认开启（AI 识别提示/总结句，中央大字随机动画）。
    emphasis_lines = config.get("emphasis_lines")
    if emphasis_lines is not None and not isinstance(emphasis_lines, dict):
        raise WorkflowStepError("production_config.emphasis_lines 必须是对象")
    if emphasis_lines is None:
        emphasis_settings = dict(DEFAULT_EMPHASIS_LINES)
    else:
        emphasis_settings = {**DEFAULT_EMPHASIS_LINES, **emphasis_lines}
        unknown = set(emphasis_lines) - {
            "enabled", "font_size", "primary_color", "highlight_color",
            "outline_color", "outline", "bold", "center_ratio", "line_height",
            "animations", "animation_duration",
            "ai_detect", "seed", "groups",
        }
        if unknown:
            raise WorkflowStepError(
                f"production_config.emphasis_lines 含未知字段：{sorted(unknown)}"
            )
    return {
        "bgm_path": Path(bgm_path),
        "bgm_gain": bgm_gain,
        "bgm_credit": str(config.get("bgm_credit") or "").strip() or None,
        "intro": intro,
        "intro_sfx_path": Path(str(config["intro_sfx_path"])) if config.get("intro_sfx_path") else None,
        "cover_frame_seconds": cover_frame_seconds,
        "shot_stickers": tuple(str(item) for item in stickers),
        "subtitle_position": subtitle_position,
        "subtitle_style": subtitle_style,
        "secondary_subtitles": secondary_settings,
        "emphasis_lines": emphasis_settings,
        "hook_lines": hook_lines,
        "hook_subtitle_position": hook_subtitle_position,
        "hook_title_text": str(config.get("hook_title_text") or "").strip(),
        # 2026-09-24 用户要求标题换行由宿主 LLM 语义决定：传了就用传入的行，
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
        "chapter_timeline": chapter_settings,
    }

