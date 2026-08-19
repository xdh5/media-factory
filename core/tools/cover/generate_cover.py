"""从候选镜头图里随机抽一张，用书法字体把标题刻上封面。"""

from __future__ import annotations

import colorsys
import random
import re
from pathlib import Path
from uuid import uuid4

from PIL import Image, ImageDraw, ImageFont, ImageOps

from ._constants import (
    DEFAULT_COVER_FONT_PATH,
    DEFAULT_COVER_SIZE,
    DOUYIN_THUMB_ASPECT,
    GOLD_HUE_MAX,
    GOLD_HUE_MIN,
    GOLD_SATURATION_MIN,
    LINE_SPACING,
    MAX_FONT_SIZE,
    MIN_FONT_SIZE,
    MIN_LUMINANCE_CONTRAST,
    SAMPLE_STEP,
    SIMILAR_HUE_DEGREES,
    STROKE_RATIO,
    TEXT_PALETTE,
    TITLE_INSET_BOTTOM,
    TITLE_INSET_TOP,
    TITLE_INSET_X,
    TITLE_VERTICAL_BIAS,
)
from ._errors import CoverFontError, CoverRenderError, CoverSourceImageError, InvalidParameterError

__all__ = ["generate_cover"]


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


def _load_font(font_path: Path, size: int) -> ImageFont.FreeTypeFont:
    try:
        return ImageFont.truetype(str(font_path), size=size)
    except OSError as exc:
        raise CoverFontError(f"无法加载封面字体：{font_path}。{exc}") from exc


def _cover_fit(image: Image.Image, width: int, height: int) -> Image.Image:
    fitted = ImageOps.fit(image.convert("RGB"), (width, height), method=Image.Resampling.LANCZOS)
    return fitted


def _title_box(width: int, height: int) -> tuple[int, int, int, int]:
    """计算抖音 3:4 中心小图内的标题排版区。"""
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


def _rgb_to_hsv(color: tuple[int, int, int]) -> tuple[float, float, float]:
    red, green, blue = (channel / 255.0 for channel in color)
    hue, saturation, value = colorsys.rgb_to_hsv(red, green, blue)
    return hue * 360.0, saturation, value


def _luminance(color: tuple[int, int, int]) -> float:
    red, green, blue = (channel / 255.0 for channel in color)
    return 0.2126 * red + 0.7152 * green + 0.0722 * blue


def _hue_distance(left: float, right: float) -> float:
    delta = abs(left - right)
    return min(delta, 360.0 - delta)


def _is_gold_like(hue: float, saturation: float, value: float) -> bool:
    return GOLD_HUE_MIN <= hue <= GOLD_HUE_MAX and saturation >= GOLD_SATURATION_MIN and value >= 0.35


def _theme_color(image: Image.Image, box: tuple[int, int, int, int]) -> tuple[int, int, int]:
    left, top, right, bottom = box
    region = image.crop((left, top, right, bottom)).resize(
        (max(8, (right - left) // SAMPLE_STEP), max(8, (bottom - top) // SAMPLE_STEP)),
        Image.Resampling.BOX,
    )
    pixels = list(region.getdata())
    if not pixels:
        return (80, 70, 55)
    count = len(pixels)
    red = sum(pixel[0] for pixel in pixels) // count
    green = sum(pixel[1] for pixel in pixels) // count
    blue = sum(pixel[2] for pixel in pixels) // count
    return (red, green, blue)


def _pick_text_colors(theme: tuple[int, int, int]) -> tuple[tuple[int, int, int], tuple[int, int, int]]:
    theme_hue, theme_sat, _theme_val = _rgb_to_hsv(theme)
    theme_luma = _luminance(theme)
    scored: list[tuple[float, str, tuple[int, int, int]]] = []
    for name, rgb in TEXT_PALETTE.items():
        hue, saturation, _value = _rgb_to_hsv(rgb)
        if _is_gold_like(theme_hue, theme_sat, _theme_val) and name == "gold":
            continue
        if theme_sat > 0.2 and saturation > 0.2 and _hue_distance(theme_hue, hue) < SIMILAR_HUE_DEGREES:
            continue
        contrast = abs(_luminance(rgb) - theme_luma)
        if contrast < MIN_LUMINANCE_CONTRAST:
            continue
        scored.append((contrast, name, rgb))
    if not scored:
        fill = TEXT_PALETTE["cream"] if theme_luma < 0.5 else TEXT_PALETTE["ink"]
    else:
        scored.sort(reverse=True)
        fill = scored[0][2]
    stroke = TEXT_PALETTE["ink"] if _luminance(fill) > 0.5 else TEXT_PALETTE["paper"]
    return fill, stroke


def _wrap_title(title: str, font: ImageFont.FreeTypeFont, max_width: int) -> list[str]:
    text = title.strip()
    if not text or font.getlength(text) <= max_width:
        return [text or title]
    marks = set("，。；、 ,.!?;:")
    max_chars = 1
    for index in range(1, len(text) + 1):
        if font.getlength(text[:index]) <= max_width:
            max_chars = index
        else:
            break
    line_count = max(2, (len(text) + max_chars - 1) // max_chars)
    while True:
        base, extra = divmod(len(text), line_count)
        lines: list[str] = []
        start = 0
        for line_index in range(line_count):
            take = base + (1 if line_index < extra else 0)
            end = min(len(text), start + take)
            if line_index < line_count - 1 and end < len(text) and text[end] in marks:
                end += 1
            piece = text[start:end].strip()
            if piece:
                lines.append(piece)
            start = end
        if start < len(text):
            leftover = text[start:].strip()
            if leftover:
                if lines and font.getlength(lines[-1] + leftover) <= max_width:
                    lines[-1] += leftover
                else:
                    lines.append(leftover)
        if lines and all(font.getlength(line) <= max_width for line in lines):
            return lines
        line_count += 1
        if line_count > len(text):
            return list(text)


def _fit_layout(
    title: str,
    font_path: Path,
    box: tuple[int, int, int, int],
) -> tuple[ImageFont.FreeTypeFont, list[str], int, int]:
    left, top, right, bottom = box
    max_width = right - left
    max_height = bottom - top
    for size in range(MAX_FONT_SIZE, MIN_FONT_SIZE - 1, -2):
        font = _load_font(font_path, size)
        lines = _wrap_title(title, font, max_width)
        spacing = int(size * LINE_SPACING)
        heights = [font.getbbox(line)[3] - font.getbbox(line)[1] for line in lines]
        total_height = sum(heights) + spacing * (len(lines) - 1)
        if total_height <= max_height and all(font.getlength(line) <= max_width for line in lines):
            return font, lines, spacing, size
    font = _load_font(font_path, MIN_FONT_SIZE)
    return font, _wrap_title(title, font, max_width), int(MIN_FONT_SIZE * LINE_SPACING), MIN_FONT_SIZE


def _draw_title(
    image: Image.Image,
    lines: list[str],
    font: ImageFont.FreeTypeFont,
    font_size: int,
    spacing: int,
    box: tuple[int, int, int, int],
    fill: tuple[int, int, int],
    stroke: tuple[int, int, int],
) -> None:
    draw = ImageDraw.Draw(image)
    left, top, right, bottom = box
    box_width = right - left
    heights = [font.getbbox(line)[3] - font.getbbox(line)[1] for line in lines]
    total_height = sum(heights) + spacing * (len(lines) - 1)
    slack = bottom - top - total_height
    cursor_y = top + max(0, int(slack * (0.5 + TITLE_VERTICAL_BIAS)))
    stroke_width = max(2, int(font_size * STROKE_RATIO))
    for line, line_height in zip(lines, heights):
        line_width = font.getlength(line)
        x = left + max(0, int((box_width - line_width) / 2))
        draw.text(
            (x, cursor_y),
            line,
            font=font,
            fill=fill,
            stroke_width=stroke_width,
            stroke_fill=stroke,
        )
        cursor_y += line_height + spacing


def generate_cover(
    images: list[str | Path],
    title: str,
    output_path: str | Path,
    *,
    size: str = DEFAULT_COVER_SIZE,
    font_path: str | Path | None = None,
    seed: int | None = None,
) -> dict:
    """随机抽一张底图，按背景主题色选对比色，用飞波正点体刻上标题。"""
    normalized_title = str(title or "").strip()
    if not normalized_title:
        raise InvalidParameterError("title", "title 必须是非空字符串")
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
    theme = _theme_color(canvas, box)
    fill, stroke = _pick_text_colors(theme)
    font, lines, spacing, font_size = _fit_layout(normalized_title, resolved_font, box)
    _draw_title(canvas, lines, font, font_size, spacing, box, fill, stroke)
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
        "fill_color": list(fill),
        "stroke_color": list(stroke),
        "theme_color": list(theme),
        "lines": lines,
    }
