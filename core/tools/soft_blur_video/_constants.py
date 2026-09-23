"""轻微磨砂玻璃滤镜常量。"""

from __future__ import annotations

# 素材重编码参数：与 generate_final_video 的 copy 拼接约定保持一致
SOFT_BLUR_VERSION = 4
SOFT_BLUR_FPS = 30
SOFT_BLUR_CODEC = "libx264"
SOFT_BLUR_PRESET = "veryfast"
SOFT_BLUR_CRF = 21
SOFT_BLUR_PIXEL_FORMAT = "yuv420p"

# 磨砂"白蒙版"参数（参考：整屏蒙一层半透明白色蒙版，像隔着白玻璃看画面）：
# - 白蒙版 alpha：白色以该不透明度整屏覆盖（发白褪色的主来源）
# - 对比/饱和度略降：配合白蒙版加强褪色质感
# - 高斯模糊 sigma：轻微糊化
# v4：比 v3（alpha 0.30 / sigma 0.75 / contrast 0.82）稍清晰一档
# 2026-09-23 试过 alpha 0.34（"再多蒙 10%"）后用户确认回到原值 0.24，沿用 v4 设定。
SOFT_BLUR_WHITE_ALPHA = 0.24
SOFT_BLUR_CONTRAST = 0.85
SOFT_BLUR_SATURATION = 0.78
SOFT_BLUR_SIGMA = 0.55

SOFT_BLUR_WORKERS = 4
SOFT_BLUR_PROBE_TIMEOUT_SECONDS = 30
SOFT_BLUR_MIN_TIMEOUT_SECONDS = 600
SOFT_BLUR_TIMEOUT_PER_SECOND = 15
