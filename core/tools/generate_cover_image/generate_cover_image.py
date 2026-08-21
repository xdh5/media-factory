"""从候选镜头图里随机抽一张，刻上长标题，产出封面图片。"""

from __future__ import annotations

import random
import re
from pathlib import Path
from uuid import uuid4

from PIL import Image, ImageDraw, ImageFont, ImageOps

from ._constants import (
    DEFAULT_COVER_FONT_PATH,
    DEFAULT_COVER_SIZE,
    DOUYIN_THUMB_ASPECT,
    LINE_SPACING,
    MAX_FONT_SIZE,
    MIN_FONT_SIZE,
    STROKE_WIDTH,
    TITLE_FILL_COLOR,
    TITLE_INSET_BOTTOM,
    TITLE_INSET_TOP,
    TITLE_INSET_X,
    TITLE_SHADOW_COLOR,
    TITLE_SHADOW_OFFSET_X,
    TITLE_SHADOW_OFFSET_Y,
    TITLE_STROKE_COLOR,
    TITLE_VERTICAL_BIAS,
)
from ._errors import CoverFontError, CoverRenderError, CoverSourceImageError, InvalidParameterError

__all__ = ["generate_cover_image"]


def _parse_size(size: str) -> tuple[int, int, str]:
    matched = re.fullmatch(r"\s*(\d+)\s*[xX×]\s*(\d+)\s*", str(size or ""))
    if not matched:
        raise InvalidParameterError("size", "size 必须使用 WIDTHxHEIGHT 格式，例如 1920x1080")
    width, height = (int(value) for value in matched.groups())
    if width < 64 or height < 64:
        raise InvalidParameterError("size", "size 的宽高都必须不小于 64 像素")
    return width, height, f"{width}x{height}"


def _validate_images(images: list[str | Path]) -> list[Path]:
    if not isinstance(images, list) or not images:
        raise InvalidParameterError("images", "images 必须是非空路径列表")
    resolved: list[Path] = []
    seen: set[Path] = set()
    for item in images:
        path = Path(str(item)).resolve()
        if path in seen:
            continue
        if not path.is_file():
            raise CoverSourceImageError(f"封面候选图不存在：{path}")
        seen.add(path)
        resolved.append(path)
    if not resolved:
        raise InvalidParameterError("images", "images 里没有可用的图片路径")
    return resolved


def _normalize_lines(title: str, lines: list[str] | None) -> list[str]:
    if lines is None:
        text = str(title or "").strip()
        if not text:
            raise InvalidParameterError("title", "title 必须是非空字符串")
        return [text]
    if not isinstance(lines, list) or not lines:
        raise InvalidParameterError("lines", "lines 必须是 Agent 断好的非空行列表")
    normalized = [str(item).strip() for item in lines]
    if any(not item for item in normalized):
        raise InvalidParameterError("lines", "lines 里不能有空行")
    compact_title = re.sub(r"\s+", "", str(title or ""))
    compact_lines = re.sub(r"\s+", "", "".join(normalized))
    if compact_title and compact_lines != compact_title:
        raise InvalidParameterError(
            "lines",
            "lines 去掉空白后必须拼回 title/长标题原文，不要增删字",
        )
    return normalized


def _load_font(font_path: Path, size: int) -> ImageFont.FreeTypeFont:
    try:
        return ImageFont.truetype(str(font_path), size=size)
    except OSError as exc:
        raise CoverFontError(f"无法加载封面字体：{font_path}。{exc}") from exc


def _cover_fit(image: Image.Image, width: int, height: int) -> Image.Image:
    return ImageOps.fit(image.convert("RGB"), (width, height), method=Image.Resampling.LANCZOS)


def _title_box(width: int, height: int) -> tuple[int, int, int, int]:
    crop_width = min(width, int(round(height * DOUYIN_THUMB_ASPECT)))
    crop_left = (width - crop_width) // 2
    pad_x = int(round(crop_width * TITLE_INSET_X))
    pad_top = int(round(height * TITLE_INSET_TOP))
    pad_bottom = int(round(height * TITLE_INSET_BOTTOM))
    left = crop_left + pad_x
    right = crop_left + crop_width - pad_x
    top = pad_top
    bottom = height - pad_bottom
    if right <= left or bottom <= top:
        return crop_left, 0, crop_left + crop_width, height
    return left, top, right, bottom


def _fit_layout(
    lines: list[str],
    font_path: Path,
    box: tuple[int, int, int, int],
) -> tuple[ImageFont.FreeTypeFont, int, int]:
    left, top, right, bottom = box
    max_width = right - left
    max_height = bottom - top
    for size in range(MAX_FONT_SIZE, MIN_FONT_SIZE - 1, -2):
        font = _load_font(font_path, size)
        spacing = int(size * LINE_SPACING)
        heights = [font.getbbox(line)[3] - font.getbbox(line)[1] for line in lines]
        total_height = sum(heights) + spacing * (len(lines) - 1)
        if total_height <= max_height and all(font.getlength(line) <= max_width for line in lines):
            return font, spacing, size
    font = _load_font(font_path, MIN_FONT_SIZE)
    return font, int(MIN_FONT_SIZE * LINE_SPACING), MIN_FONT_SIZE


def _draw_title(
    image: Image.Image,
    lines: list[str],
    font: ImageFont.FreeTypeFont,
    spacing: int,
    box: tuple[int, int, int, int],
) -> None:
    overlay = Image.new("RGBA", image.size, (0, 0, 0, 0))
    shadow_draw = ImageDraw.Draw(overlay)
    draw = ImageDraw.Draw(image)
    left, top, right, bottom = box
    box_width = right - left
    heights = [font.getbbox(line)[3] - font.getbbox(line)[1] for line in lines]
    total_height = sum(heights) + spacing * (len(lines) - 1)
    slack = bottom - top - total_height
    start_y = top + max(0, int(slack * (0.5 + TITLE_VERTICAL_BIAS)))
    stroke_width = STROKE_WIDTH
    cursor_y = start_y
    for line, line_height in zip(lines, heights):
        line_width = font.getlength(line)
        x = left + max(0, int((box_width - line_width) / 2))
        shadow_draw.text(
            (x + TITLE_SHADOW_OFFSET_X, cursor_y + TITLE_SHADOW_OFFSET_Y),
            line,
            font=font,
            fill=TITLE_SHADOW_COLOR,
            stroke_width=stroke_width,
            stroke_fill=TITLE_SHADOW_COLOR,
        )
        cursor_y += line_height + spacing
    image.paste(Image.alpha_composite(image.convert("RGBA"), overlay).convert("RGB"))
    cursor_y = start_y
    for line, line_height in zip(lines, heights):
        line_width = font.getlength(line)
        x = left + max(0, int((box_width - line_width) / 2))
        draw.text(
            (x, cursor_y),
            line,
            font=font,
            fill=TITLE_FILL_COLOR,
            stroke_width=stroke_width,
            stroke_fill=TITLE_STROKE_COLOR,
        )
        cursor_y += line_height + spacing


def generate_cover_image(
    images: list[str | Path],
    title: str,
    output_path: str | Path,
    *,
    size: str = DEFAULT_COVER_SIZE,
    font_path: str | Path | None = None,
    seed: int | None = None,
    lines: list[str] | None = None,
) -> dict:
    """随机抽一张底图，用典迹题幕刻金黄字、黑描边和右下浅阴影。断行由调用方传入 lines，工具只缩放字号不自动折行。"""
    normalized_title = str(title or "").strip()
    if not normalized_title:
        raise InvalidParameterError("title", "title 必须是非空字符串")
    drawn_lines = _normalize_lines(normalized_title, lines)
    candidates = _validate_images(images)
    width, height, normalized_size = _parse_size(size)
    resolved_font = Path(font_path or DEFAULT_COVER_FONT_PATH).resolve()
    if not resolved_font.is_file():
        raise CoverFontError(f"封面字体不存在：{resolved_font}")
    picker = random.Random(seed)
    source_path = picker.choice(candidates)
    try:
        with Image.open(source_path) as source:
            source.load()
            canvas = _cover_fit(source, width, height)
    except (OSError, ValueError) as exc:
        raise CoverSourceImageError(f"无法读取封面底图：{source_path}。{exc}") from exc
    box = _title_box(width, height)
    font, spacing, font_size = _fit_layout(drawn_lines, resolved_font, box)
    _draw_title(canvas, drawn_lines, font, spacing, box)
    destination = Path(output_path).resolve()
    destination.parent.mkdir(parents=True, exist_ok=True)
    temporary = destination.with_name(f".{destination.stem}-{uuid4().hex}.tmp.png")
    try:
        canvas.save(temporary, format="PNG")
        temporary.replace(destination)
    except OSError as exc:
        raise CoverRenderError(f"写入封面失败：{destination}。{exc}") from exc
    finally:
        if temporary.exists():
            temporary.unlink(missing_ok=True)
    return {
        "output_path": str(destination),
        "source_image_path": str(source_path),
        "title": normalized_title,
        "size": normalized_size,
        "font_path": str(resolved_font),
        "fill_color": list(TITLE_FILL_COLOR),
        "stroke_color": list(TITLE_STROKE_COLOR),
        "theme_color": list(TITLE_FILL_COLOR),
        "lines": drawn_lines,
    }
