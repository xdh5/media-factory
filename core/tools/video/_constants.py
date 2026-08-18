"""视频合成工具常量。

字幕版式由原文生图配置等比例换算为 1280×720 默认配置。
"""

VIDEO_RENDERER_VERSION = 10
BASE_VIDEO_WIDTH = 1280
BASE_VIDEO_HEIGHT = 720
VIDEO_FPS = 30
VIDEO_CODEC = "libx264"
VIDEO_PRESET = "veryfast"
VIDEO_CRF = 21
VIDEO_PIXEL_FORMAT = "yuv420p"
VIDEO_AUDIO_CODEC = "aac"
VIDEO_AUDIO_RATE = 48_000
VIDEO_AUDIO_CHANNELS = 2
VIDEO_MOTION_SUPERSAMPLE = 1
VIDEO_RENDER_MIN_TIMEOUT_SECONDS = 180
VIDEO_RENDER_TIMEOUT_PER_SECOND = 15
VIDEO_FFMPEG_TIMEOUT_SECONDS = 600
VIDEO_PROBE_TIMEOUT_SECONDS = 30

# 成品文件名默认使用标题；仅替换 Windows 不允许的字符，保留正常中文标题。
WINDOWS_FORBIDDEN_FILENAME_CHARACTERS = '<>:"/\\|?*'
WINDOWS_RESERVED_FILENAMES = {
    "CON", "PRN", "AUX", "NUL",
    *{f"COM{number}" for number in range(1, 10)},
    *{f"LPT{number}" for number in range(1, 10)},
}
MAX_OUTPUT_FILENAME_STEM_LENGTH = 120

SUBTITLE_MAX_LINES = 2
SUBTITLE_CANVAS_WIDTH_RATIO = 0.8
SUBTITLE_STYLES = {
    "zh": {
        "language": "zh",
        "font": "Microsoft YaHei",
        "font_size_ratio": 68 / 1080,
        "alignment": 2,
        "margin_vertical_ratio": 128 / 1080,
        "outline_ratio": 4 / 1080,
        "shadow_ratio": 1 / 1080,
    },
    "en": {
        "language": "en",
        "font": "DejaVu Sans",
        "font_size_ratio": 68 / 1080,
        "alignment": 2,
        "margin_vertical_ratio": 128 / 1080,
        "outline_ratio": 4 / 1080,
        "shadow_ratio": 1 / 1080,
    },
}
SUPPORTED_SUBTITLE_LANGUAGES = list(SUBTITLE_STYLES)

# ai-video-maker 通过 Docker 挂载 Windows 字体；存在时优先让 libass 扫描该目录。
SUBTITLE_FONT_DIRECTORIES = ["/usr/share/fonts/windows"]
