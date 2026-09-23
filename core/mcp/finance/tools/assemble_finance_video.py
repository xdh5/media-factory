"""财经成片：封面、片头镜头与最终合成。

同一套合成流程支持三类素材策略：
- 图库选图 / 参考图生图：正文镜头用静态图（由 compose_shots 渲染成片）；
- 正版实拍视频：正文镜头用已裁好的视频片段，片头仍是写实静态图 + 转场动画。
"""

from __future__ import annotations

import hashlib
import json
import random
from datetime import datetime, timezone
from pathlib import Path

from core.tools.generate_cover_image import CoverError, generate_cover_image
from core.tools.cloudflare_data import commit_production_outputs
from core.tools.generate_final_video import generate_final_video, safe_filename
from core.tools.generate_final_video._defaults import (
    DEFAULT_HOOK_LINES,
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
from core.tools.generate_final_video._ffmpeg import _probe
from core.tools.generate_final_video._size import parse_size
from core.tools.generate_subtitles import generate_subtitles
from core.tools.generate_subtitles._constants import SUBTITLE_FONT_DIRECTORY
from core.tools.generate_shot import (
    INTRO_RENDERER_VERSION,
    SFX_SHUTTER_GAIN,
    SFX_SHUTTER_PATH,
    SFX_SHUTTER_SECONDS,
    SFX_ALERT_GAIN,
    SFX_ALERT_PATH,
    SFX_ALERT_SECONDS,
    SHUTTER_START_SECONDS,
    ShotToolError,
    generate_shot_from_intro,
    intro_bgm_start_seconds,
)
from core.tools.stock_video import prepare_stock_clip

from .._constants import (
    CONTENT_KIND,
    MATERIAL_STOCK_VIDEO,
    MATRIXMEDIA_AI_CREATIVE_STATEMENT,
    MCP_ID,
    STORYBOARD_TEXT_FILE_NAME,
    TOPIC_DEDUPLICATION_DAYS,
    publish_date_from_run_id,
    VIDEO_SIZE,
)
from .._errors import WorkflowStepError
from .narration import bare_text, display_subtitle_cue, display_subtitle_text
from .save_draft import load_draft
from .storyboard import load_prepared_tts, parse_storyboard


def _raw_source_hints(manifest: dict, cache_root: Path) -> dict[str, Path]:
    """按素材清单的署名记录定位每个镜头当初选中的原始素材。

    raw 目录里同时留着同一镜头的多个候选（搜索阶段下载的备选），
    只按文件名排序取第一个会在重裁时把镜头换成没被选中的候选，
    所以优先用 attribution 里的 provider + source_id 还原真实素材。
    """
    hints: dict[str, Path] = {}
    for item in manifest.get("attributions") or []:
        if not isinstance(item, dict):
            continue
        shot_id = str(item.get("video_id") or "").strip()
        provider = str(item.get("provider") or "").strip()
        source_id = str(item.get("source_id") or "").strip()
        if not (shot_id and provider and source_id):
            continue
        candidate = cache_root / "stock-videos" / "raw" / f"{shot_id}-{provider}-{source_id}.mp4"
        if candidate.is_file():
            hints[shot_id] = candidate
    return hints


def _ensure_clip_durations(
    shots: list[dict],
    cache_root: Path,
    progress=None,
    raw_hints: dict[str, Path] | None = None,
) -> None:
    """片段时长与当前分镜不符时，从原始素材重裁。

    配音换音色/改语速后时间轴会变，而 clips 是按旧时长裁好的缓存；
    不重裁会让成片总长与配音不匹配（画面、字幕对不上，末尾配音被截）。
    """
    hints = raw_hints or {}
    for shot in shots:
        clip = Path(str(shot.get("segment_path") or ""))
        if not clip.is_file():
            continue
        try:
            available = float(_probe(clip)["duration"])
        except Exception:
            continue
        target = float(shot.get("duration") or 0)
        if target <= 0 or abs(available - target) <= 0.05:
            continue
        hinted = hints.get(shot["id"])
        raw_candidates = [hinted] if hinted else sorted(
            (cache_root / "stock-videos" / "raw").glob(f"{shot['id']}-*.mp4")
        )
        if not raw_candidates:
            raise WorkflowStepError(
                f"镜头 {shot['id']} 时长已变（{available:.2f}s -> {target:.2f}s），但找不到原始素材无法重裁"
            )
        if progress:
            progress(f"重裁镜头 {shot['id']}：{available:.2f}s -> {target:.2f}s")
        prepare_stock_clip(
            raw_candidates[0],
            clip,
            target,
            size=VIDEO_SIZE,
            frame_path=cache_root / "stock-videos" / "frames" / f"{shot['id']}.png",
        )


def _positive_int(value, field: str) -> int:
    if value is None:
        return 0
    if isinstance(value, bool) or not isinstance(value, int) or value < 0:
        raise WorkflowStepError(f"production_config.{field} 必须是非负整数")
    return value


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
    if bgm_gain is not None:
        try:
            bgm_gain = float(bgm_gain)
        except (TypeError, ValueError) as exc:
            raise WorkflowStepError("production_config.bgm_gain 必须是数字") from exc
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
        "matrixmedia_account_group": account_group,
        "hook_lines": hook_lines,
        "hook_subtitle_position": hook_subtitle_position,
        "hook_title_text": str(config.get("hook_title_text") or "").strip(),
        "hook_title_style": hook_title_style,
        "hook_title_position": hook_title_position,
        "hook_title_single_color": hook_title_single_color,
        "hook_title_first_line_color": hook_title_first_line_color,
        "hook_title_other_line_color": hook_title_other_line_color,
        "hook_title_dark_outline": hook_title_dark_outline,
        "hook_title_light_outline": hook_title_light_outline,
        "hook_title_line_height": hook_title_line_height,
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


def _split_title_lines(text: str, max_chars: int) -> list[str]:
    """标题按标点断行（标点不入行）；断不开的超宽行再按宽度硬切。"""
    text = str(text or "").strip()
    if not text:
        return []
    parts: list[str] = []
    current = ""
    for char in text:
        if char in _HOOK_TITLE_BREAK_CHARS:
            if current.strip():
                parts.append(current.strip())
            current = ""
        else:
            current += char
    if current.strip():
        parts.append(current.strip())
    lines: list[str] = []
    for part in parts:
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
) -> list[str]:
    """钩子标题图层：一行一个 ASS，按行配色并用 \\pos 垂直堆叠居中。

    单行：红字黑边；多行：第一行字幕黄黑边，其余行红字白边。
    """
    title_style = dict(settings["hook_title_style"])
    try:
        font_size = max(1, int(title_style.get("font_size") or 110))
    except (TypeError, ValueError):
        font_size = 110
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
    title_text = settings["hook_title_text"] or metadata["title"]
    canvas_width, canvas_height = parse_size(VIDEO_SIZE)
    return _hook_title_layers(
        title_text, hook_end, settings, canvas_width, canvas_height, cache_root
    )


def _hash_file(path: str | Path) -> str:
    digest = hashlib.sha256()
    with Path(path).open("rb") as source:
        for chunk in iter(lambda: source.read(1024 * 1024), b""):
            digest.update(chunk)
    return digest.hexdigest()


def _resolve_intro_sfx(path: Path | None) -> Path | None:
    if path is None:
        return None
    if path.is_file():
        return path
    parent = path.parent
    stem = path.stem
    for suffix in (".wav", ".mp3", ".m4a", ".aac", ".ogg"):
        candidate = parent / f"{stem}{suffix}"
        if candidate.is_file():
            return candidate
    return path


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


def _slide_in_opening_sfx() -> list[dict]:
    items = []
    if SFX_ALERT_PATH.is_file():
        items.append({
            "path": str(SFX_ALERT_PATH),
            "start": 0.0,
            "duration": SFX_ALERT_SECONDS,
            "gain": SFX_ALERT_GAIN,
        })
    if SFX_SHUTTER_PATH.is_file():
        items.append({
            "path": str(SFX_SHUTTER_PATH),
            "start": SHUTTER_START_SECONDS,
            "duration": SFX_SHUTTER_SECONDS,
            "gain": SFX_SHUTTER_GAIN,
        })
    return items


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
    sfx_path = _resolve_intro_sfx(intro_sfx_path)
    if intro == "page_flip":
        pool = [
            str(item.get("image_path") or item.get("frame_path") or "")
            for item in shots
        ]
        pool = [path for path in pool if path]
        seed = "|".join([MCP_ID, shot["id"]] + [_hash_file(path) for path in pool])
        page_images = _pick_page_flip_images(pool, shot["image_path"], seed)
    metadata_path = segment_path.with_suffix(".json")
    payload = {
        "version": 4,
        "intro": intro,
        "intro_renderer_version": INTRO_RENDERER_VERSION,
        "image_sha256": _hash_file(shot["image_path"]),
        "page_image_sha256": [_hash_file(path) for path in page_images],
        "sfx_sha256": _hash_file(sfx_path) if intro == "page_flip" and sfx_path and sfx_path.is_file() else None,
        "alert_sha256": _hash_file(SFX_ALERT_PATH) if intro == "slide_in_shutter" and SFX_ALERT_PATH.is_file() else None,
        "duration": shot["duration"],
        "motion": shot["motion"],
    }
    signature = hashlib.sha256(
        json.dumps(payload, ensure_ascii=False, sort_keys=True, separators=(",", ":")).encode("utf-8")
    ).hexdigest()
    if not force and segment_path.is_file() and metadata_path.is_file():
        try:
            metadata = json.loads(metadata_path.read_text(encoding="utf-8"))
            if metadata.get("signature") == signature:
                opening_sfx = list(metadata.get("opening_sfx") or [])
                if not opening_sfx and intro == "slide_in_shutter":
                    opening_sfx = _slide_in_opening_sfx()
                return True, opening_sfx
        except (OSError, ValueError, json.JSONDecodeError):
            pass
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
            motion=shot["motion"],
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


def _storyboard_hash(value: str) -> str:
    return hashlib.sha256(value.encode("utf-8")).hexdigest()


def _load_saved_storyboard(
    material_metadata: dict,
    cache_root: Path,
    storyboard_text: str | None,
) -> str:
    saved = str(material_metadata.get("storyboard_text") or "").strip()
    saved_path = Path(str(material_metadata.get("storyboard_path") or "")).resolve()
    if not saved and saved_path.is_file():
        saved = saved_path.read_text(encoding="utf-8").strip()
    fallback_path = cache_root / STORYBOARD_TEXT_FILE_NAME
    if not saved and fallback_path.is_file():
        saved = fallback_path.read_text(encoding="utf-8").strip()
    if saved:
        expected_hash = str(material_metadata.get("storyboard_sha256") or "").strip()
        if expected_hash and _storyboard_hash(saved) != expected_hash:
            raise WorkflowStepError(
                "已保存的分镜文本损坏，请重新准备镜头素材",
                {"storyboard_sha256": expected_hash},
            )
        return saved
    fallback = str(storyboard_text or "").strip()
    if not fallback:
        raise WorkflowStepError(
            "素材清单里没有分镜文本。请重新调用 finance_prepare_images / finance_start_video_search，出片不必再传 storyboard_text"
        )
    expected_hash = str(material_metadata.get("storyboard_sha256") or "").strip()
    if expected_hash and _storyboard_hash(fallback) != expected_hash:
        raise WorkflowStepError(
            "传入的 storyboard_text 与准备素材时不一致。请重新准备素材后直接 finance_finish_video",
            {"storyboard_sha256": expected_hash, "received_sha256": _storyboard_hash(fallback)},
        )
    return fallback


def _apply_material(
    manifest: dict,
    shots: list[dict],
    *,
    resolved_draft: Path,
    intro_image_path: str | Path | None,
    cache_root: Path,
    progress,
) -> tuple[bool, list[str]]:
    """按素材清单类型挂载镜头，返回 (是否实拍视频策略, 封面源图)。"""
    material_metadata = manifest.get("metadata")
    if not isinstance(material_metadata, dict):
        raise WorkflowStepError("素材清单缺少 metadata")
    if Path(str(material_metadata.get("draft_path") or "")).resolve() != resolved_draft:
        raise WorkflowStepError("素材清单不属于当前稿件，请重新准备镜头素材")
    videos = manifest.get("videos")
    if isinstance(videos, dict) and videos:
        frames = manifest.get("frames")
        if len(shots) < 2:
            raise WorkflowStepError("分镜至少需要两个镜头：片头动画后必须有正文视频素材")
        expected_ids = {shot["id"] for shot in shots[1:]}
        if set(videos) != expected_ids:
            raise WorkflowStepError(
                "视频素材清单没有完整覆盖所有镜头",
                {"expected_video_ids": sorted(expected_ids), "actual_video_ids": sorted(videos)},
            )
        if not isinstance(frames, dict) or set(frames) != expected_ids:
            raise WorkflowStepError("视频素材清单缺少完整封面帧")
        for video_id, video_path in videos.items():
            if not Path(str(video_path)).resolve().is_file():
                raise WorkflowStepError(f"视频素材不存在：{video_id} -> {video_path}")
        for shot in shots[1:]:
            shot["segment_path"] = str(Path(videos[shot["id"]]).resolve())
            shot["frame_path"] = str(Path(frames[shot["id"]]).resolve())
        _ensure_clip_durations(shots[1:], cache_root, progress, _raw_source_hints(manifest, cache_root))
        if not intro_image_path:
            raise WorkflowStepError("实拍视频策略必须传 intro_image_path 指向片头写实图")
        resolved_intro_image = Path(intro_image_path).resolve()
        if not resolved_intro_image.is_file():
            raise WorkflowStepError(f"片头写实图不存在：{resolved_intro_image}")
        shots[0]["image_path"] = str(resolved_intro_image)
        shots[0]["frame_path"] = str(resolved_intro_image)
        return True, [str(shot["frame_path"]) for shot in shots]
    images = manifest.get("images")
    expected_image_ids = {shot["id"] for shot in shots}
    if not isinstance(images, dict) or set(images) != expected_image_ids:
        raise WorkflowStepError(
            "选图清单没有完整覆盖所有镜头",
            {"expected_image_ids": sorted(expected_image_ids), "actual_image_ids": sorted(images or {})},
        )
    for image_id, image_path in images.items():
        if not Path(str(image_path)).resolve().is_file():
            raise WorkflowStepError(f"选图清单中的图片不存在：{image_id} -> {image_path}")
    for shot in shots:
        shot["image_path"] = str(Path(images[shot["id"]]).resolve())
        shot["frame_path"] = str(Path(images[shot["id"]]).resolve())
    return False, [str(shot["image_path"]) for shot in shots]


def _write_attributions(
    manifest: dict,
    settings: dict,
    output_root: Path,
) -> str | None:
    attributions = list(manifest.get("attributions") or [])
    if not attributions:
        return None
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
    if settings.get("bgm_credit"):
        attribution_lines.append(str(settings["bgm_credit"]))
    path = output_root / "attribution-comment.txt"
    path.write_text("\n".join(attribution_lines) + "\n", encoding="utf-8")
    return str(path)


def finish_finance_video(
    draft_path: str | Path,
    *,
    material_manifest_path: str | Path | None = None,
    production_config: dict,
    intro_image_path: str | Path | None = None,
    storyboard_text: str | None = None,
    force_shot_ids: list[str] | None = None,
    production_source: str = "local_mcp",
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
    record = {"id": draft["topic_record_id"], "topic": draft["topic"]}
    content_kind = str(draft.get("content_kind") or CONTENT_KIND)
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
        cover = generate_cover_image(
            cover_sources,
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
            extra_ass_paths=extra_ass_paths,
            normalize_composed=stock_video,
            progress=progress,
        )
    except Exception as extra:
        raise WorkflowStepError(f"财经成片失败：{extra}") from extra
    final_path = Path(final_result["output_path"])
    publish_date = publish_date_from_run_id(run_id)
    production_outputs = None
    if production_source == "local_mcp":
        production_outputs = commit_production_outputs([{
            "production_id": f"local_mcp:finance:{run_id}:{content_kind}:1",
            "run_id": run_id,
            "publish_date": publish_date,
            "business_line": "finance",
            "content_kind": content_kind,
            "content_part": 1,
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
        "status": "awaiting_publish_confirmation",
        "confirmation_required": "publish",
        "line": MCP_ID,
        "content_kind": content_kind,
        "material_strategy": material_strategy,
        "intro_image_path": (
            str(first_shot["image_path"]) if stock_video else None
        ),
        "topic": record["topic"],
        "run_id": run_id,
        "article": article,
        **metadata,
        "cover_path": cover["output_path"],
        "video_path": str(final_path),
        "cache_dir": str(cache_root),
        "output_dir": str(output_root),
        "title_path": str(title_path),
        "short_title_path": str(short_title_path),
        "publish_bt2": metadata["short_title"],
        "publish_copy": publish_copy,
        "publish_copy_path": str(publish_copy_path),
        "attribution_comment_path": attribution_comment_path,
        "stock_video_attributions": list(material_manifest.get("attributions") or []),
        "matrixmedia_account_group": settings["matrixmedia_account_group"],
        "creativeStatement": MATRIXMEDIA_AI_CREATIVE_STATEMENT,
        "created_at": created_at,
        "publish_date": publish_date,
        "production_source": production_source,
        "production_outputs": production_outputs,
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
