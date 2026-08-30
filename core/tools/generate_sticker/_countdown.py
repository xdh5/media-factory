"""经典 3、2、1 扫圆盘倒计时贴纸：透明单次 MOV。"""

from __future__ import annotations

import shutil
import subprocess
import tempfile
from pathlib import Path

from PIL import Image, ImageDraw, ImageFont

from ._constants import (
    COUNTDOWN_CENTER_Y,
    COUNTDOWN_CIRCLE_COLOR,
    COUNTDOWN_DIAMETER,
    COUNTDOWN_DIGITS,
    COUNTDOWN_FONT_PATH,
    COUNTDOWN_NUMBER_COLOR,
    COUNTDOWN_NUMBER_FONT_SIZE,
    COUNTDOWN_ONE_OPTICAL_OFFSET_X,
    COUNTDOWN_NUMBER_STROKE_COLOR,
    COUNTDOWN_REFERENCE_HEIGHT,
    COUNTDOWN_REFERENCE_WIDTH,
    COUNTDOWN_WEDGE_COLOR,
    STICKER_FFMPEG_TIMEOUT_SECONDS,
    STICKER_FPS,
)
from ._errors import FFmpegNotFoundError, RenderError, RenderTimeoutError, StickerFontError

__all__ = ["write_countdown_sticker"]


def _layout(canvas_width: int, canvas_height: int) -> dict:
    scale = canvas_height / COUNTDOWN_REFERENCE_HEIGHT
    diameter = max(120, round(COUNTDOWN_DIAMETER * scale))
    if diameter % 2:
        diameter += 1
    x = max(0, (canvas_width - diameter) // 2)
    center_y = round(COUNTDOWN_CENTER_Y * scale)
    y = max(0, min(canvas_height - diameter, center_y - diameter // 2))
    font_size = max(48, round(COUNTDOWN_NUMBER_FONT_SIZE * scale))
    if not COUNTDOWN_FONT_PATH.is_file():
        raise StickerFontError(str(COUNTDOWN_FONT_PATH))
    return {
        "width": diameter,
        "height": diameter,
        "x": x,
        "y": y,
        "font": ImageFont.truetype(str(COUNTDOWN_FONT_PATH), size=font_size),
    }


def _draw_frame(layout: dict, frame_index: int, frame_count: int) -> Image.Image:
    image = Image.new("RGBA", (layout["width"], layout["height"]), (0, 0, 0, 0))
    draw = ImageDraw.Draw(image)
    width, height = image.size
    center = (width // 2, height // 2)
    radius = min(width, height) // 2 - 4
    box = (center[0] - radius, center[1] - radius, center[0] + radius, center[1] + radius)
    digit_index = min(len(COUNTDOWN_DIGITS) - 1, frame_index * len(COUNTDOWN_DIGITS) // frame_count)
    digit_start = digit_index * frame_count / len(COUNTDOWN_DIGITS)
    digit_progress = min(
        1.0,
        (frame_index - digit_start + 1) / (frame_count / len(COUNTDOWN_DIGITS)),
    )
    draw.pieslice(
        box,
        start=-90,
        end=-90 + 360 * digit_progress,
        fill=COUNTDOWN_WEDGE_COLOR,
    )
    circle_width = max(3, round(width * 0.03))
    draw.ellipse(box, outline=COUNTDOWN_CIRCLE_COLOR, width=circle_width)
    inner = max(5, round(width * 0.05))
    draw.ellipse(
        (box[0] + inner, box[1] + inner, box[2] - inner, box[3] - inner),
        outline=COUNTDOWN_CIRCLE_COLOR,
        width=max(2, circle_width // 2),
    )
    draw.line((0, center[1], width, center[1]), fill=COUNTDOWN_CIRCLE_COLOR, width=max(2, circle_width // 2))
    draw.line((center[0], 0, center[0], height), fill=COUNTDOWN_CIRCLE_COLOR, width=max(2, circle_width // 2))
    digit = str(COUNTDOWN_DIGITS[digit_index])
    stroke_width = max(1, round(width * 0.012))
    text_box = draw.textbbox(
        (0, 0),
        digit,
        font=layout["font"],
        stroke_width=stroke_width,
    )
    text_position = (
        round(
            center[0]
            - (text_box[0] + text_box[2]) / 2
            + (COUNTDOWN_ONE_OPTICAL_OFFSET_X if digit == "1" else 0)
        ),
        round(center[1] - (text_box[1] + text_box[3]) / 2),
    )
    draw.text(
        text_position,
        digit,
        font=layout["font"],
        fill=COUNTDOWN_NUMBER_COLOR,
        stroke_width=stroke_width,
        stroke_fill=COUNTDOWN_NUMBER_STROKE_COLOR,
    )
    return image


def write_countdown_sticker(
    destination: Path,
    canvas_width: int,
    canvas_height: int,
    duration: float,
) -> dict:
    layout = _layout(canvas_width, canvas_height)
    ffmpeg = shutil.which("ffmpeg")
    if not ffmpeg:
        raise FFmpegNotFoundError("ffmpeg")
    frame_count = max(len(COUNTDOWN_DIGITS), round(duration * STICKER_FPS))
    rendered_duration = frame_count / STICKER_FPS
    destination.parent.mkdir(parents=True, exist_ok=True)
    with tempfile.TemporaryDirectory(prefix="generate-sticker-countdown-", dir=destination.parent) as temporary:
        root = Path(temporary)
        for frame_index in range(frame_count):
            _draw_frame(layout, frame_index, frame_count).save(root / f"frame-{frame_index:04d}.png")
        command = [
            ffmpeg, "-y",
            "-framerate", str(STICKER_FPS),
            "-i", str(root / "frame-%04d.png"),
            "-an", "-c:v", "qtrle", "-pix_fmt", "argb",
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
        except subprocess.TimeoutExpired as exc:
            raise RenderTimeoutError("生成倒计时贴图", STICKER_FFMPEG_TIMEOUT_SECONDS) from exc
        if completed.returncode != 0:
            detail = (completed.stderr or completed.stdout or "").strip()[-3000:]
            raise RenderError(f"生成倒计时贴图失败：{detail or '未知 FFmpeg 错误'}")
    return {
        "width": layout["width"],
        "height": layout["height"],
        "x": layout["x"],
        "y": layout["y"],
        "loop": False,
        "duration": rendered_duration,
    }
