"""开场动画（双向滑入 + 快门闪光）常量配置。"""

from __future__ import annotations

from pathlib import Path

# 输出画面：1280x720（ffmpeg scale/crop 用冒号，color 画布用 x）
OUTPUT_WIDTH = 1280
OUTPUT_HEIGHT = 720
OUTPUT_SIZE = f"{OUTPUT_WIDTH}:{OUTPUT_HEIGHT}"
CANVAS_SIZE = f"{OUTPUT_WIDTH}x{OUTPUT_HEIGHT}"
RESOLUTION = CANVAS_SIZE
FPS = 30
INTRO_RENDERER_VERSION = 8

# 片头包含多层 2560x1440 叠加、阴影模糊和音效混音，不能沿用普通镜头的
# 超时策略；弱 CPU 下也应给一次完整编码机会，但避免无限等待。
INTRO_RENDER_MIN_TIMEOUT_SECONDS = 180
INTRO_RENDER_TIMEOUT_PER_SECOND = 30

# 滑入时序（秒）
FIRST_SLIDE_SECONDS = 0.675       # 黑白全画幅自左滑入时长
SECOND_SLIDE_START_SECONDS = 0.0  # 彩色照片卡开始滑入的时刻
SLIDE_IN_SECONDS = 0.675          # 双向滑入动画总时长
HOLD_SECONDS = 0.5                # 滑入完成后的停顿时长

# 小图像（彩色照片卡）相对原图的比例
CARD_SCALE = 0.5

# 快门时序（秒）
SHUTTER_START_SECONDS = SLIDE_IN_SECONDS + HOLD_SECONDS  # 快门/闪光时刻
FLASH_SECONDS = 0.18              # 白色闪光时长
PHOTO_EXPAND_SECONDS = 0.5        # 快门后彩色全屏从中心向四周展开的时长
# 开场完整时长：滑入、停顿、闪光、四向展开；之后无切镜交给首镜头原动效。
TOTAL_SECONDS = SHUTTER_START_SECONDS + FLASH_SECONDS + PHOTO_EXPAND_SECONDS

# 照片卡柔和投影
CARD_SHADOW_MARGIN = 64           # 投影外边距（像素）
CARD_SHADOW_OFFSET_X = 16         # 投影水平偏移
CARD_SHADOW_OFFSET_Y = 24         # 投影垂直偏移
CARD_SHADOW_OPACITY = 0.52        # 投影不透明度
CARD_SHADOW_BLUR = 27             # 投影高斯模糊半径

# 开场音效（模块内 static 目录，随滤镜时序对齐）
_STATIC_DIR = Path(__file__).resolve().parent / "static"
SFX_WHOOSH_PATH = _STATIC_DIR / "whoosh.wav"   # 滑入音效：从 0 播到 SLIDE_IN_SECONDS
SFX_SHUTTER_PATH = _STATIC_DIR / "shutter.wav"  # 快门音效：SHUTTER_START_SECONDS 时刻播放
SFX_WHOOSH_SECONDS = SLIDE_IN_SECONDS  # 滑入音效截取时长
SFX_WHOOSH_GAIN = 1.35            # 滑入“嗖”声音量增益
SFX_SHUTTER_SECONDS = 0.456       # 快门音效截取时长
SFX_SHUTTER_GAIN = 1.8            # 快门音效增益
