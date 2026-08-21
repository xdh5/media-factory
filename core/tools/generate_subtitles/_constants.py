"""生成 ASS 字幕常量。

默认版式：左右各留 10%、底中、距底 10%；固定 100px 加粗白字黑边。
默认字体：普推黑体（`static/font/PUTUI-Regular.ttf`）。
"""

from __future__ import annotations

from pathlib import Path


def _project_root() -> Path:
    for candidate in Path(__file__).resolve().parents:
        if (candidate / "AGENTS.md").is_file():
            return candidate
    raise RuntimeError("找不到项目根目录：缺少 AGENTS.md")


SUBTITLE_FONT_DIRECTORY = _project_root() / "static" / "font"
SUBTITLE_DEFAULT_FONT_PATH = SUBTITLE_FONT_DIRECTORY / "PUTUI-Regular.ttf"
SUBTITLE_DEFAULT_FONT_FAMILY = "PUTUI"
SUBTITLE_DEFAULT_FONT_SIZE = 100

SUBTITLE_MAX_LINES = 2
SUBTITLE_HORIZONTAL_MARGIN_RATIO = 0.1
SUBTITLE_CANVAS_WIDTH_RATIO = 1 - SUBTITLE_HORIZONTAL_MARGIN_RATIO * 2
SUBTITLE_BOTTOM_MARGIN_RATIO = 0.1
SUBTITLE_OUTLINE_RATIO = 0.004
SUBTITLE_SHADOW_RATIO = 0.0
SUBTITLE_DEFAULT_COLORS = {
    "primary_color": "&H00FFFFFF",
    "secondary_color": "&H00FFFFFF",
    "outline_color": "&H00000000",
    "back_color": "&H00000000",
}
SUPPORTED_SUBTITLE_ALIGNMENTS = list(range(1, 10))
SUBTITLE_STYLES = {
    "zh": {
        "language": "zh",
        "font": SUBTITLE_DEFAULT_FONT_FAMILY,
        "font_size": SUBTITLE_DEFAULT_FONT_SIZE,
        "bold": True,
        "alignment": 2,
        "margin_vertical_ratio": SUBTITLE_BOTTOM_MARGIN_RATIO,
        "outline_ratio": SUBTITLE_OUTLINE_RATIO,
        "shadow_ratio": SUBTITLE_SHADOW_RATIO,
    },
    "en": {
        "language": "en",
        "font": SUBTITLE_DEFAULT_FONT_FAMILY,
        "font_size": SUBTITLE_DEFAULT_FONT_SIZE,
        "bold": True,
        "alignment": 2,
        "margin_vertical_ratio": SUBTITLE_BOTTOM_MARGIN_RATIO,
        "outline_ratio": SUBTITLE_OUTLINE_RATIO,
        "shadow_ratio": SUBTITLE_SHADOW_RATIO,
    },
}
SUPPORTED_SUBTITLE_LANGUAGES = list(SUBTITLE_STYLES)
