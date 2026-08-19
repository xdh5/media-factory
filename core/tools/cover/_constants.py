"""封面刻字工具常量。"""

from pathlib import Path

_ROOT = Path(__file__).resolve().parent
DEFAULT_COVER_FONT_PATH = _ROOT / "static" / "feibo-zhengdian.otf"
DEFAULT_COVER_SIZE = "1920x1080"
# 抖音资料页会从横屏正中裁出 3:4 小图，标题必须落在该裁切区内。
DOUYIN_THUMB_ASPECT = 3 / 4
# 相对 3:4 裁切区的内边距：左右留白；排版区略靠上，标题在区内水平居中、垂直偏上。
TITLE_INSET_X = 0.06
TITLE_INSET_TOP = 0.08
TITLE_INSET_BOTTOM = 0.22
TITLE_VERTICAL_BIAS = -0.12
MIN_FONT_SIZE = 42
MAX_FONT_SIZE = 150
LINE_SPACING = 0.18
STROKE_RATIO = 0.06
SAMPLE_STEP = 6
MIN_LUMINANCE_CONTRAST = 0.28
SIMILAR_HUE_DEGREES = 25.0
GOLD_HUE_MIN = 25.0
GOLD_HUE_MAX = 55.0
GOLD_SATURATION_MIN = 0.25
TEXT_PALETTE = {
    "ink": (28, 22, 16),
    "deep_navy": (18, 32, 52),
    "cream": (245, 232, 204),
    "ivory": (255, 250, 240),
    "gold": (212, 175, 90),
    "paper": (248, 244, 236),
}
