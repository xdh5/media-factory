"""生成 ASS 字幕常量。

默认版式：左右各留 10%、底中、距底 10%；固定 100px 加粗白字黑边。
默认字体：普推黑体（`static/font/PUTUI-Regular.ttf`）。
"""

from __future__ import annotations

from pathlib import Path


def _project_root() -> Path:
    for candidate in Path(__file__).resolve().parents:
        if any((candidate / name).is_file() for name in ("AGENTS.md", "agents.md")):
            return candidate
    raise RuntimeError("找不到项目根目录：缺少 AGENTS.md 或 agents.md")


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

# 爆款字幕预设：移植自 ai-video-captions 的 6 套 TikTok/Reels 样式，
# 字号/描边/阴影按其竖版 1920 高基准换算为比例，适配任意分辨率。
# 字体不内置（预设里的 Montserrat 等未必安装），沿用语言默认字体，可用 style.font 覆盖。
# animation：highlight=重点词换色 / karaoke=颜色从左到右扫过 / scale=当前词放大 / bounce=当前词弹跳。
# uppercase 只影响拉丁字符，中文无副作用。
SUBTITLE_PRESETS = {
    "hormozi": {
        "style": {
            "font_size_ratio": 0.055,
            "outline_ratio": 0.0026,
            "shadow_ratio": 0.0023,
            "primary_color": "#FFFFFF",
            "bold": True,
            "italic": False,
        },
        "highlight_color": "#00FFFF",
        "animation": "highlight",
        "uppercase": True,
    },
    "mrbeast": {
        "style": {
            "font_size_ratio": 0.0625,
            "outline_ratio": 0.0042,
            "shadow_ratio": 0.0031,
            "primary_color": "#FFFF00",
            "bold": True,
            "italic": False,
        },
        "highlight_color": "#FF6600",
        "animation": "highlight",
        "uppercase": True,
    },
    "karaoke": {
        "style": {
            "font_size_ratio": 0.055,
            "outline_ratio": 0.0021,
            "shadow_ratio": 0.0016,
            "primary_color": "#FFFFFF",
            "bold": True,
            "italic": False,
        },
        "highlight_color": "#0080FF",
        "animation": "karaoke",
        "uppercase": True,
    },
    "minimal": {
        "style": {
            "font_size_ratio": 0.0625,
            "outline_ratio": 0.0021,
            "shadow_ratio": 0.0016,
            "primary_color": "#FFFFFF",
            "bold": True,
            "italic": True,
            "letter_spacing": 3.0,
        },
        "highlight_color": "#F5F5F5",
        "animation": "scale",
        "uppercase": False,
    },
    "bounce": {
        "style": {
            "font_size_ratio": 0.057,
            "outline_ratio": 0.0026,
            "shadow_ratio": 0.0026,
            "primary_color": "#00FF88",
            "bold": True,
            "italic": False,
        },
        "highlight_color": "#FF00FF",
        "animation": "bounce",
        "uppercase": True,
    },
    "classic": {
        "style": {
            "font_size_ratio": 0.055,
            "outline_ratio": 0.0031,
            "shadow_ratio": 0.0016,
            "primary_color": "#FFFFFF",
            "bold": True,
            "italic": False,
        },
        "highlight_color": "#FFFF00",
        "animation": "highlight",
        "uppercase": True,
    },
}
SUPPORTED_SUBTITLE_PRESETS = list(SUBTITLE_PRESETS)
SUPPORTED_SUBTITLE_ANIMATIONS = ["highlight", "karaoke", "scale", "bounce"]
