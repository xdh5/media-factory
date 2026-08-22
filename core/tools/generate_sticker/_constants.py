"""生成贴图素材常量。

REC 是可选贴图之一：以 1080p 为基准按画布高度缩放，左上红圆闪烁 + 常亮 REC 字。
"""

from __future__ import annotations

from pathlib import Path

def _project_root() -> Path:
    for candidate in Path(__file__).resolve().parents:
        if any((candidate / name).is_file() for name in ("AGENTS.md", "agents.md")):
            return candidate
    raise RuntimeError("找不到项目根目录：缺少 AGENTS.md 或 agents.md")


STICKER_REC = "rec"
SUPPORTED_STICKERS = (STICKER_REC,)

STICKER_FFMPEG_TIMEOUT_SECONDS = 60
STICKER_FPS = 30

REC_FONT_PATH = _project_root() / "static" / "font" / "ArialMdm.ttf"
REC_REFERENCE_HEIGHT = 1080
REC_MARGIN_X = 36
REC_MARGIN_Y = 28
REC_CIRCLE_DIAMETER = 27
REC_TEXT_FONT_SIZE = 72
REC_DOT_TEXT_GAP = 11
REC_TEXT_COLOR = (255, 255, 255, 255)
REC_CIRCLE_COLOR = (255, 45, 45, 255)
REC_BG_COLOR = (0, 0, 0, 153)
REC_BG_PAD_X = 21
REC_BG_PAD_Y = 11
REC_BG_RADIUS = 15
REC_LETTER_SPACING = 3
REC_BLINK_CYCLE_SECONDS = 1.0
REC_BLINK_ON_SECONDS = 0.5
