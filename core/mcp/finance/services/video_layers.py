"""财经字幕、标题与章节图层。"""

from __future__ import annotations

from pathlib import Path
from core.tools.generate_final_video._size import parse_size
from core.tools.generate_subtitles import generate_subtitles
from core.tools.generate_subtitles._constants import SUBTITLE_FONT_DIRECTORY
from core.tools.generate_timeline import fallback_chapter_titles, generate_chapter_timeline, generate_chapter_titles
from ..config.settings import VIDEO_SIZE
from ..errors import WorkflowStepError
from .narration import bare_text, display_subtitle_cue, display_subtitle_text


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


def _row_text(row) -> str:
    if not isinstance(row, dict):
        return ""
    text = row.get("text")
    if isinstance(text, list):
        return "".join(str(seg.get("text") or "") for seg in text if isinstance(seg, dict))
    return str(text or "")


def _auto_hook_lines(rows: list, source_hook: str) -> int:
    """按稿件黄金钩子自动确定钩子占用的台词行数。"""
    hook = bare_text(source_hook)
    if not hook or not rows:
        return 0
    accumulated = ""
    for index, row in enumerate(rows, 1):
        accumulated += bare_text(_row_text(row))
        if len(accumulated) >= len(hook):
            return index if accumulated.startswith(hook) else len(rows)
    return len(rows)


_HOOK_TITLE_BREAK_CHARS = "，。！？；：、,.!?;:…"


_FONT_METRICS_CACHE: dict[str, tuple[float, float, Path] | None] = {}


_LINE_INK_CACHE: dict[tuple[str, str], tuple[float, float] | None] = {}


def _title_font_metrics(font_name: str) -> tuple[float, float, Path] | None:
    """按族名在 static/font 里找字体文件，返回 (ascent_ratio, descent_ratio, 路径)。

    descent 为负值；fontTools 缺失或找不到字体时返回 None（跳过墨迹居中校正）。
    """
    key = str(font_name or "").strip()
    if not key:
        return None
    if key in _FONT_METRICS_CACHE:
        return _FONT_METRICS_CACHE[key]
    result: tuple[float, float, Path] | None = None
    try:
        from fontTools.ttLib import TTFont
    except ImportError:
        TTFont = None
    if TTFont is not None:
        for candidate in sorted(SUBTITLE_FONT_DIRECTORY.iterdir()):
            if candidate.suffix.lower() not in {".ttf", ".otf", ".ttc"}:
                continue
            matched = candidate.stem.lower() == key.lower()
            if not matched:
                try:
                    font = TTFont(str(candidate), fontNumber=0, lazy=True)
                    names = set()
                    for record in font["name"].names:
                        if record.nameID in (1, 4, 6, 16):
                            try:
                                names.add(record.toUnicode().strip().lower())
                            except Exception:
                                pass
                    font.close()
                    matched = key.lower() in names
                except Exception:
                    continue
            if not matched:
                continue
            try:
                font = TTFont(str(candidate), fontNumber=0, lazy=True)
                upem = int(font["head"].unitsPerEm) or 1000
                ascent = float(font["hhea"].ascent) / upem
                descent = float(font["hhea"].descent) / upem
                font.close()
            except Exception:
                continue
            if ascent > 0 > descent:
                result = (ascent, descent, candidate)
            break
    _FONT_METRICS_CACHE[key] = result
    return result


def _line_ink_ratios(font_path: Path, text: str) -> tuple[float, float] | None:
    """返回 (ink_top_ratio, ink_bottom_ratio)：整行墨迹相对基线上/下的高度（比例 × 字号 = 像素）。"""
    key = (str(font_path), text)
    if key in _LINE_INK_CACHE:
        return _LINE_INK_CACHE[key]
    result: tuple[float, float] | None = None
    try:
        from fontTools.pens.boundsPen import BoundsPen
        from fontTools.ttLib import TTFont

        font = TTFont(str(font_path), fontNumber=0, lazy=True)
        cmap = font.getBestCmap() or {}
        glyph_set = font.getGlyphSet()
        upem = int(font["head"].unitsPerEm) or 1000
        top = bottom = 0.0
        for char in text:
            glyph_name = cmap.get(ord(char))
            if glyph_name is None:
                continue
            pen = BoundsPen(glyph_set)
            glyph_set[glyph_name].draw(pen)
            if pen.bounds is None:
                continue
            _, y_min, _, y_max = pen.bounds
            top = max(top, y_max / upem)
            bottom = max(bottom, -y_min / upem)
        font.close()
        if top > 0:
            result = (top, bottom)
    except Exception:
        result = None
    _LINE_INK_CACHE[key] = result
    return result


def _center_title_ink(
    lines: list[str],
    ys: list[int],
    font_name: str,
    font_size: int,
    canvas_height: int,
    target_ratio: float,
) -> list[int]:
    """按整块标题的真实墨迹做视觉居中。

    libass 的 an5 锚点基于 ascent+descent 行盒（本字体 1.2em），书法体墨迹相对锚点偏下，
    直接按几何行盒堆叠整块会低 ~20px；这里用 fontTools 量出每行墨迹后整体平移校正。
    """
    metrics = _title_font_metrics(font_name)
    if metrics is None:
        return ys
    ascent_ratio, descent_ratio, font_path = metrics
    inks = [_line_ink_ratios(font_path, line) for line in lines]
    if any(ink is None for ink in inks):
        return ys
    baseline_shift = (ascent_ratio + descent_ratio) / 2 * font_size
    tops: list[float] = []
    bottoms: list[float] = []
    for y, (ink_top, ink_bottom) in zip(ys, inks, strict=True):
        baseline = y + baseline_shift
        tops.append(baseline - ink_top * font_size)
        bottoms.append(baseline + ink_bottom * font_size)
    delta = canvas_height * target_ratio - (min(tops) + max(bottoms)) / 2
    return [round(y + delta) for y in ys]


def _hook_title_lines_override(raw) -> list[str] | None:
    """校验宿主 LLM 传入的标题分行（1~3 行非空字符串）；不传返回 None。"""
    if raw is None:
        return None
    if not isinstance(raw, list) or not raw or len(raw) > 3:
        raise WorkflowStepError("production_config.hook_title_lines 必须是 1~3 行的非空字符串列表")
    lines = [str(item).strip() for item in raw]
    if any(not line for line in lines):
        raise WorkflowStepError("production_config.hook_title_lines 里不能有空行")
    return lines


def _split_title_parts(text: str) -> list[str]:
    """标题按标点切段（标点不入段）。"""
    parts: list[str] = []
    current = ""
    for char in str(text or "").strip():
        if char in _HOOK_TITLE_BREAK_CHARS:
            if current.strip():
                parts.append(current.strip())
            current = ""
        else:
            current += char
    if current.strip():
        parts.append(current.strip())
    return parts


def _split_title_lines(text: str, max_chars: int) -> list[str]:
    """标题按标点断行（标点不入行）；断不开的超宽行再按宽度硬切。"""
    text = str(text or "").strip()
    if not text:
        return []
    lines: list[str] = []
    for part in _split_title_parts(text):
        while len(part) > max_chars:
            lines.append(part[:max_chars])
            part = part[max_chars:]
        if part:
            lines.append(part)
    return lines


def _hook_title_layers(
    title_text: str,
    hook_end: float,
    settings: dict,
    canvas_width: int,
    canvas_height: int,
    cache_root: Path,
    *,
    title_lines: list[str] | None = None,
) -> list[str]:
    """钩子标题图层：一行一个 ASS，按行配色并用 \\pos 垂直堆叠居中。

    单行：红字黑边；多行：第一行字幕黄黑边，其余行红字白边。
    """
    title_style = dict(settings["hook_title_style"])
    try:
        font_size = max(1, int(title_style.get("font_size") or 110))
    except (TypeError, ValueError):
        font_size = 110
    override_lines = settings.get("hook_title_lines")
    if override_lines:
        # 宿主 LLM 已语义断行：直接用传入的行，超宽时缩字号保住整行不拆词。
        longest = max(len(line) for line in override_lines)
        if longest > 0:
            fit_size = int(canvas_width * 0.8 // longest)
            if fit_size >= 1:
                font_size = min(font_size, fit_size)
        lines = list(override_lines)
    else:
        max_chars = max(1, int(canvas_width * 0.8 // font_size))
        lines = _split_title_lines(title_text, max_chars)
    if not lines:
        return []
    multi = len(lines) > 1
    line_height = round(font_size * float(settings["hook_title_line_height"]))
    base_position = dict(settings["hook_title_position"])
    target_ratio = float(base_position.pop("margin_vertical_ratio", 0.5) or 0.5)
    base_position.pop("margin_vertical", None)
    base_position["x"] = canvas_width // 2
    ys = [
        round(canvas_height * target_ratio)
        + round((index - (len(lines) - 1) / 2) * line_height)
        for index in range(len(lines))
    ]
    ys = _center_title_ink(
        lines,
        ys,
        str(title_style.get("font") or ""),
        font_size,
        canvas_height,
        target_ratio,
    )
    paths: list[str] = []
    for index, line in enumerate(lines):
        if multi and index == 0:
            color, outline = settings["hook_title_first_line_color"], settings["hook_title_dark_outline"]
        elif multi:
            color, outline = settings["hook_title_other_line_color"], settings["hook_title_light_outline"]
        else:
            color, outline = settings["hook_title_single_color"], settings["hook_title_dark_outline"]
        style = {**title_style, "primary_color": color, "outline_color": outline}
        position = {
            **base_position,
            "y": ys[index],
        }
        try:
            layer = generate_subtitles(
                [{"start": 0.0, "end": hook_end, "text": line}],
                cache_root / f"hook-title-{index + 1}.ass",
                canvas_width,
                canvas_height,
                style=style,
                position=position,
            )
        except Exception as exc:
            raise WorkflowStepError(f"生成钩子标题图层失败：{exc}") from exc
        paths.append(layer["output_path"])
    return paths


def _hook_layer(
    video_shots: list[dict],
    settings: dict,
    metadata: dict,
    source_hook: str,
    cache_root: Path,
) -> list[str]:
    """黄金钩子：第一个镜头的前 N 行字幕改放到钩子位置，并生成居中标题图层。"""
    if not video_shots:
        return []
    all_rows = video_shots[0].get("subtitle_lines") or []
    hook_lines = settings["hook_lines"]
    if hook_lines is None:
        hook_lines = _auto_hook_lines(all_rows, source_hook)
    if hook_lines <= 0:
        return []
    hook_rows = all_rows[:hook_lines]
    hook_end = 0.0
    for row in hook_rows:
        if isinstance(row, dict):
            row["position"] = settings["hook_subtitle_position"]
    if hook_rows and isinstance(hook_rows[-1], dict):
        try:
            hook_end = float(hook_rows[-1].get("end") or 0.0)
        except (TypeError, ValueError):
            hook_end = 0.0
    if hook_end <= 0:
        return []
    # 2026-09-24 用户要求第一镜头钩子标题用短标题，标题缺失时回退全称。
    title_text = settings["hook_title_text"] or metadata.get("short_title") or metadata["title"]
    canvas_width, canvas_height = parse_size(VIDEO_SIZE)
    return _hook_title_layers(
        title_text,
        hook_end,
        settings,
        canvas_width,
        canvas_height,
        cache_root,
        title_lines=settings["hook_title_lines"],
    )


def _chapter_groups(shots: list[dict], count: int) -> list[list[dict]]:
    """把镜头按时长均分成 count 个连续章节组（边界落在镜头边缘）。"""
    target = sum(float(shot["duration"]) for shot in shots) / count
    groups: list[list[dict]] = []
    current: list[dict] = [shots[0]]
    accumulated = float(shots[0]["duration"])
    for shot in shots[1:]:
        if accumulated >= target and len(groups) < count - 1:
            groups.append(current)
            current = []
            accumulated = 0.0
        current.append(shot)
        accumulated += float(shot["duration"])
    if current:
        groups.append(current)
    return [group for group in groups if group]


def _chapter_layer(
    shots: list[dict],
    settings: dict,
    cache_root: Path,
    progress=None,
) -> list[str]:
    """章节时间轴条图层：横条分段 + AI 段落标题 + 进度色随播放推进。"""
    chapter = settings["chapter_timeline"]
    if not chapter.get("enabled") or len(shots) < 2:
        return []
    count = max(2, min(int(chapter["segment_count"]), len(shots)))
    groups = _chapter_groups(shots, count)
    if len(groups) < 2:
        return []
    segments = []
    chapter_texts = []
    for group in groups:
        start = float(group[0]["audio_start"])
        end = float(group[-1]["audio_end"])
        if end - start < 1.0:
            continue
        segments.append({"start": start, "end": end, "title": ""})
        chapter_texts.append(
            " ".join(str(shot.get("subtitle") or "") for shot in group)
        )
    if len(segments) < 2:
        return []
    if chapter.get("ai_titles", True):
        titles = generate_chapter_titles(chapter_texts, progress=progress)
    else:
        titles = fallback_chapter_titles(chapter_texts)
    for segment, title in zip(segments, titles, strict=True):
        segment["title"] = title
    canvas_width, canvas_height = parse_size(VIDEO_SIZE)
    try:
        layer = generate_chapter_timeline(
            segments,
            cache_root / "chapter-timeline.ass",
            canvas_width,
            canvas_height,
            position=str(chapter["position"]),
            style={
                key: chapter[key]
                for key in (
                    "font_size",
                    "bar_height",
                    "margin_horizontal",
                    "margin_vertical_ratio",
                )
                if key in chapter
            },
        )
    except Exception as exc:
        raise WorkflowStepError(f"生成章节时间轴条失败：{exc}") from exc
    if progress is not None:
        progress(
            "章节时间轴条（{}，{} 段）：{}".format(
                layer["position"], layer["segment_count"], "、".join(layer["titles"])
            )
        )
    return [layer["output_path"]]

