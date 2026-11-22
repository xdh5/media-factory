"""财经字幕、钩子标题与片头效果。"""

from __future__ import annotations
from pathlib import Path
from fontTools.pens.boundsPen import BoundsPen
from fontTools.ttLib import TTFont
from tools.generate_final_video._size import parse_size
from tools.generate_subtitles import generate_subtitles
from tools.generate_subtitles._constants import SUBTITLE_FONT_DIRECTORY
from workflows.finance.parameters import VIDEO_SIZE, MCP_ID
from workflows.finance.errors.exceptions import WorkflowStepError
from workflows.finance.tools.drafts import bare_text
from workflows.finance.tools.storyboard import display_subtitle_cue, display_subtitle_text
import hashlib, json, random
from tools.generate_shot import (
    INTRO_RENDERER_VERSION,
    SFX_ALERT_PATH,
    ShotToolError,
    generate_shot_from_intro,
)


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


_FONT_METRICS_CACHE: dict[str, tuple[float, float, Path]] = {}


_LINE_INK_CACHE: dict[tuple[str, str], tuple[float, float] | None] = {}


def _title_font_metrics(font_name: str) -> tuple[float, float, Path]:
    """按族名读取包内字体的基线参数。"""
    key = font_name.strip().lower()
    if key in _FONT_METRICS_CACHE:
        return _FONT_METRICS_CACHE[key]
    for candidate in sorted(SUBTITLE_FONT_DIRECTORY.iterdir()):
        if candidate.suffix.lower() not in {".ttf", ".otf", ".ttc"}:
            continue
        with TTFont(str(candidate), fontNumber=0, lazy=True) as font:
            names = {record.toUnicode().strip().lower()
                     for record in font["name"].names if record.nameID in (1, 4, 6, 16)}
            if candidate.stem.lower() != key and key not in names:
                continue
            upem = font["head"].unitsPerEm
            result = (font["hhea"].ascent / upem, font["hhea"].descent / upem, candidate)
        _FONT_METRICS_CACHE[key] = result
        return result
    raise WorkflowStepError(f"找不到标题字体：{font_name}")


def _line_ink_ratios(font_path: Path, text: str) -> tuple[float, float] | None:
    """返回 (ink_top_ratio, ink_bottom_ratio)：整行墨迹相对基线上/下的高度（比例 × 字号 = 像素）。"""
    key = (str(font_path), text)
    if key in _LINE_INK_CACHE:
        return _LINE_INK_CACHE[key]
    result: tuple[float, float] | None = None
    with TTFont(str(font_path), fontNumber=0, lazy=True) as font:
        cmap = font.getBestCmap()
        glyph_set = font.getGlyphSet()
        upem = font["head"].unitsPerEm
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
        if top > 0:
            result = (top, bottom)
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


def _split_title_lines(text: str) -> list[str]:
    """只按句读断行；没有语义断点的长句保留完整，由排版层缩小字号。"""
    return _split_title_parts(text)


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
    font_size = max(1, int(title_style["font_size"]))
    override_lines = title_lines or settings.get("hook_title_lines")
    lines = list(override_lines) if override_lines else _split_title_lines(title_text)
    if not lines:
        return []
    # 完整保留语义行，不能为了字号把词语尾字拆到下一行。
    longest = max(len(line) for line in lines)
    font_size = min(font_size, max(1, int(canvas_width * 0.8 // longest)))
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
    if hook_rows:
        hook_end = float(hook_rows[-1]["end"])
    if hook_end <= 0:
        return []
    # 首镜头钩子优先使用短标题。
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


def _hash_file(path: str | Path) -> str:
    digest = hashlib.sha256()
    with Path(path).open("rb") as source:
        for chunk in iter(lambda: source.read(1024 * 1024), b""):
            digest.update(chunk)
    return digest.hexdigest()


def _pick_page_flip_images(image_paths: list[str], last_path: str, seed: str) -> list[str]:
    resolved = [str(Path(path).resolve()) for path in image_paths]
    last = str(Path(last_path).resolve())
    others = [path for path in resolved if path != last]
    pool = others or resolved
    rng = random.Random(int(hashlib.sha256(seed.encode("utf-8")).hexdigest()[:16], 16))
    pages: list[str] = []
    for _ in range(8):
        choices = [path for path in pool if not pages or path != pages[-1]] or pool
        pages.append(rng.choice(choices))
    pages.append(last)
    return pages


def _render_first_shot_cached(
    intro: str,
    intro_sfx_path: Path | None,
    shots: list[dict],
    shot: dict,
    segment_path: Path,
    *,
    force: bool,
) -> tuple[bool, list[dict]]:
    page_images: list[str] = []
    sfx_path = intro_sfx_path
    if intro == "page_flip":
        pool = [
            str(item.get("image_path") or item.get("frame_path") or "")
            for item in shots
        ]
        pool = [path for path in pool if path]
        seed = "|".join([MCP_ID, shot["id"]] + [_hash_file(path) for path in pool])
        page_images = _pick_page_flip_images(pool, shot["image_path"], seed)
    metadata_path = segment_path.with_suffix(".json")
    follow_video = str(shot.get("intro_video_path") or "").strip()
    payload = {
        "version": 5,
        "intro": intro,
        "intro_renderer_version": INTRO_RENDERER_VERSION,
        "image_sha256": _hash_file(shot["image_path"]),
        "follow_video_sha256": _hash_file(follow_video) if follow_video else "",
        "page_image_sha256": [_hash_file(path) for path in page_images],
        "sfx_sha256": _hash_file(sfx_path) if intro == "page_flip" and sfx_path and sfx_path.is_file() else None,
        "alert_sha256": _hash_file(SFX_ALERT_PATH) if intro == "slide_in_shutter" and SFX_ALERT_PATH.is_file() else None,
        "duration": shot["duration"],
        "motion": shot.get("motion"),
    }
    signature = hashlib.sha256(
        json.dumps(payload, ensure_ascii=False, sort_keys=True, separators=(",", ":")).encode("utf-8")
    ).hexdigest()
    if not force and segment_path.is_file() and metadata_path.is_file():
        metadata = json.loads(metadata_path.read_text(encoding="utf-8"))
        if metadata["signature"] == signature:
            return True, metadata["opening_sfx"]
    try:
        if intro == "page_flip" and (sfx_path is None or not Path(sfx_path).is_file()):
            raise WorkflowStepError("片头音效不存在，请在 production_config.intro_sfx_path 指向实际文件")
        rendered = generate_shot_from_intro(
            intro,
            segment_path,
            duration=shot["duration"],
            image_path=shot["image_path"],
            image_paths=page_images or None,
            sfx_path=sfx_path,
            motion=shot.get("motion"),
            video_path=follow_video or None,
        )
    except ShotToolError as extra:
        raise WorkflowStepError(extra.message, extra.details) from extra
    opening_sfx = list(rendered.get("opening_sfx") or [])
    temporary = metadata_path.with_suffix(".json.tmp")
    temporary.write_text(
        json.dumps(
            {"signature": signature, "shot_id": shot["id"], "opening_sfx": opening_sfx},
            ensure_ascii=False,
            sort_keys=True,
        ),
        encoding="utf-8",
    )
    temporary.replace(metadata_path)
    return False, opening_sfx
