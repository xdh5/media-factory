"""视频合成工具常量。

字幕版式沿用 ai-video-maker 文生图的 1920×1080 默认配置。
"""

VIDEO_RENDERER_VERSION = 3
BASE_VIDEO_WIDTH = 1920
BASE_VIDEO_HEIGHT = 1080
VIDEO_FPS = 30
VIDEO_CODEC = "libx264"
VIDEO_PRESET = "veryfast"
VIDEO_CRF = 21
VIDEO_PIXEL_FORMAT = "yuv420p"
VIDEO_AUDIO_CODEC = "aac"
VIDEO_AUDIO_RATE = 48_000
VIDEO_AUDIO_CHANNELS = 2

SUBTITLE_MAX_LINES = 2
SUBTITLE_STYLES = {
    "zh": {
        "language": "zh",
        "font": "Microsoft YaHei",
        "font_size": 68,
        "alignment": 2,
        "margin_left": 225,
        "margin_right": 225,
        "margin_vertical": 128,
        "max_width": 42,
        "outline": 4,
        "shadow": 1,
    },
    "en": {
        "language": "en",
        "font": "DejaVu Sans",
        "font_size": 68,
        "alignment": 2,
        "margin_left": 225,
        "margin_right": 225,
        "margin_vertical": 128,
        "max_width": 42,
        "outline": 4,
        "shadow": 1,
    },
}
SUPPORTED_SUBTITLE_LANGUAGES = list(SUBTITLE_STYLES)

# ai-video-maker 通过 Docker 挂载 Windows 字体；存在时优先让 libass 扫描该目录。
SUBTITLE_FONT_DIRECTORIES = ["/usr/share/fonts/windows"]
