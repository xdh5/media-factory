"""REC 贴图素材：透明循环 MOV（红圆闪烁，REC 字常亮）。"""

from __future__ import annotations

import shutil
import subprocess
import tempfile
from pathlib import Path

from PIL import Image, ImageDraw, ImageFont

from ._constants import (
    REC_BG_COLOR,
    REC_BG_PAD_X,
    REC_BG_PAD_Y,
    REC_BG_RADIUS,
    REC_BLINK_ON_SECONDS,
    REC_CIRCLE_COLOR,
    REC_CIRCLE_DIAMETER,
    REC_DOT_TEXT_GAP,
    REC_FONT_PATH,
    REC_LETTER_SPACING,
    REC_MARGIN_X,
    REC_MARGIN_Y,
    REC_REFERENCE_HEIGHT,
    REC_TEXT_COLOR,
    REC_TEXT_FONT_SIZE,
    STICKER_FFMPEG_TIMEOUT_SECONDS,
    STICKER_FPS,
)
from ._errors import FFmpegNotFoundError, RenderError, RenderTimeoutError, StickerFontError

__all__ = ["write_rec_sticker"]


def _scale(height: int) -> float:
    return max(height, 1) / REC_REFERENCE_HEIGHT


def _font(size: int) -> ImageFont.FreeTypeFont:
    if not REC_FONT_PATH.is_file():
        raise StickerFontError(str(REC_FONT_PATH))
    return ImageFont.truetype(str(REC_FONT_PATH), size=size)


def _text_metrics(font: ImageFont.FreeTypeFont, text: str, letter_spacing: int) -> tuple[int, int, int, list[tuple[str, int]]]:
    """返回加字距后的总宽、字形 top/bottom（相对绘制原点），以及每个字的 x 偏移。"""
    glyphs: list[tuple[str, int]] = []
    cursor = 0
    top: int | None = None
    bottom: int | None = None
    for index, char in enumerate(text):
        bbox = font.getbbox(char)
        if index:
            cursor += letter_spacing
        glyphs.append((char, cursor - bbox[0]))
        cursor += max(1, bbox[2] - bbox[0])
        if top is None or bottom is None:
            top, bottom = bbox[1], bbox[3]
        else:
            top = min(top, bbox[1])
            bottom = max(bottom, bbox[3])
    if top is None or bottom is None:
        top, bottom = 0, 1
    return max(1, cursor), top, bottom, glyphs


def _layout(canvas_height: int) -> dict:
    scale = _scale(canvas_height)
    text_size = max(12, round(REC_TEXT_FONT_SIZE * scale))
    diameter = max(1, round(REC_CIRCLE_DIAMETER * scale))
    radius = diameter / 2
    gap = round(REC_DOT_TEXT_GAP * scale)
    pad_x = round(REC_BG_PAD_X * scale)
    pad_y = round(REC_BG_PAD_Y * scale)
    margin_x = round(REC_MARGIN_X * scale)
    margin_y = round(REC_MARGIN_Y * scale)
    letter_spacing = round(REC_LETTER_SPACING * scale)
    font = _font(text_size)
    text_width, text_top, text_bottom, glyphs = _text_metrics(font, "REC", letter_spacing)
    text_height = max(1, text_bottom - text_top)
    content_height = max(diameter, text_height)
    center_y = pad_y + content_height / 2
    circle_y = center_y - diameter / 2
    text_y = center_y - (text_top + text_bottom) / 2
    text_x = pad_x + diameter + gap
    width = pad_x * 2 + diameter + gap + text_width
    height = pad_y * 2 + content_height
    return {
        "font": font,
        "diameter": diameter,
        "radius": radius,
        "gap": gap,
        "width": width,
        "height": height,
        "x": margin_x,
        "y": margin_y,
        "circle_x": pad_x,
        "circle_y": round(circle_y),
        "text_x": round(text_x),
        "text_y": round(text_y),
        "glyphs": glyphs,
        "radius_bg": max(2, round(REC_BG_RADIUS * scale)),
    }


def _draw_frame(layout: dict, *, circle_on: bool) -> Image.Image:
    image = Image.new("RGBA", (layout["width"], layout["height"]), (0, 0, 0, 0))
    draw = ImageDraw.Draw(image)
    draw.rounded_rectangle(
        (0, 0, layout["width"] - 1, layout["height"] - 1),
        radius=layout["radius_bg"],
        fill=REC_BG_COLOR,
    )
    if circle_on:
        left = layout["circle_x"]
        top = layout["circle_y"]
        diameter = layout["diameter"]
        draw.ellipse((left, top, left + diameter - 1, top + diameter - 1), fill=REC_CIRCLE_COLOR)
    for char, offset in layout["glyphs"]:
        draw.text(
            (layout["text_x"] + offset, layout["text_y"]),
            char,
            font=layout["font"],
            fill=REC_TEXT_COLOR,
        )
    return image


def write_rec_sticker(destination: Path, canvas_height: int) -> dict:
    layout = _layout(canvas_height)
    ffmpeg = shutil.which("ffmpeg")
    if not ffmpeg:
        raise FFmpegNotFoundError("ffmpeg")
    destination.parent.mkdir(parents=True, exist_ok=True)
    with tempfile.TemporaryDirectory(prefix="generate-sticker-rec-", dir=destination.parent) as temporary:
        root = Path(temporary)
        on_path = root / "on.png"
        off_path = root / "off.png"
        _draw_frame(layout, circle_on=True).save(on_path)
        _draw_frame(layout, circle_on=False).save(off_path)
        command = [
            ffmpeg, "-y",
            "-loop", "1", "-framerate", str(STICKER_FPS), "-t", f"{REC_BLINK_ON_SECONDS:.3f}", "-i", str(on_path),
            "-loop", "1", "-framerate", str(STICKER_FPS), "-t", f"{REC_BLINK_ON_SECONDS:.3f}", "-i", str(off_path),
            "-filter_complex",
            "[0:v]format=rgba[a];[1:v]format=rgba[b];[a][b]concat=n=2:v=1:a=0,fps="
            f"{STICKER_FPS},format=rgba",
            "-an", "-c:v", "qtrle",
            str(destination),
        ]
        try:
            completed = subprocess.run(
                command,
                check=False,
                capture_output=True,
                text=True,
                encoding="utf-8",
                errors="replace",
                timeout=STICKER_FFMPEG_TIMEOUT_SECONDS,
            )
        except subprocess.TimeoutExpired as extra:
            raise RenderTimeoutError("生成 REC 贴图", STICKER_FFMPEG_TIMEOUT_SECONDS) from extra
        if completed.returncode != 0:
            detail = (completed.stderr or completed.stdout or "").strip()[-3000:]
            raise RenderError(f"生成 REC 贴图失败：{detail or '未知 FFmpeg 错误'}")
    return {
        "width": layout["width"],
        "height": layout["height"],
        "x": layout["x"],
        "y": layout["y"],
        "loop": True,
    }
