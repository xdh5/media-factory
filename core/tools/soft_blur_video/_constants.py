"""轻微磨砂玻璃滤镜常量。"""

from __future__ import annotations

from pathlib import Path

_DIR = Path(__file__).resolve().parent

# 素材重编码参数：与 generate_final_video 的 copy 拼接约定保持一致
SOFT_BLUR_VERSION = 2
SOFT_BLUR_FPS = 30
SOFT_BLUR_CODEC = "libx264"
SOFT_BLUR_PRESET = "veryfast"
SOFT_BLUR_CRF = 21
SOFT_BLUR_PIXEL_FORMAT = "yuv420p"

# 磨砂"雾面玻璃感"参数（参考：整体发白提亮、降对比、轻微褪色 + 轻糊）：
# - 黑位抬升（雾感主来源）：把纯黑抬起来，画面像蒙了一层薄雾
# - 对比/饱和度略降、亮度微提：雾面褪色质感
# - 高斯模糊 sigma：0.75 比初版（1.2）更清晰，雾感主要靠黑位而非糊度
# 基准：参考图约等于 lift 0.12 / contrast 0.82 / sat 0.70，本参数比参考稍清晰一档
SOFT_BLUR_BLACK_LIFT = 0.09
SOFT_BLUR_CONTRAST = 0.86
SOFT_BLUR_SATURATION = 0.78
SOFT_BLUR_BRIGHTNESS = 0.04
SOFT_BLUR_SIGMA = 0.75

SOFT_BLUR_WORKERS = 4
SOFT_BLUR_PROBE_TIMEOUT_SECONDS = 30
SOFT_BLUR_MIN_TIMEOUT_SECONDS = 600
SOFT_BLUR_TIMEOUT_PER_SECOND = 15
