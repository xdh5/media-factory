"""视频合成工具常量。

字幕版式按 1920×1080 为基准用比例换算，横版财经成片默认即该尺寸。
"""

VIDEO_RENDERER_VERSION = 15
BASE_VIDEO_WIDTH = 1920
BASE_VIDEO_HEIGHT = 1080
VIDEO_FPS = 30
VIDEO_CODEC = "libx264"
VIDEO_PRESET = "veryfast"
VIDEO_CRF = 21
VIDEO_TUNE_STILLIMAGE = "stillimage"
VIDEO_PIXEL_FORMAT = "yuv420p"
VIDEO_AUDIO_CODEC = "aac"
VIDEO_AUDIO_RATE = 48_000
VIDEO_AUDIO_CHANNELS = 2
# zoompan 在目标分辨率上会把缓慢平移取整到整像素，静图会一帧一帧地抖。
# 先放到 4 倍画布上算运镜，输出 2 倍中间帧，再 lanczos 收到成品尺寸。
VIDEO_MOTION_INPUT_SCALE = 4
VIDEO_MOTION_WORK_SCALE = 2
VIDEO_RENDER_MIN_TIMEOUT_SECONDS = 360
VIDEO_RENDER_TIMEOUT_PER_SECOND = 15
# 循环静图必须有限时长，否则 -shortest 停不住，每个镜头会编满超时时间。
# 只限制画面、略长于音频，不给音频/成品加 -t，避免句尾被裁。
VIDEO_IMAGE_LOOP_PAD_SECONDS = 0.25
VIDEO_SHOT_RENDER_WORKERS = 4
VIDEO_FFMPEG_TIMEOUT_SECONDS = 600
VIDEO_PROBE_TIMEOUT_SECONDS = 30

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
