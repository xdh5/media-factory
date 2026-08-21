"""生成封面图片常量。"""

from pathlib import Path

def _project_root() -> Path:
    for candidate in Path(__file__).resolve().parents:
        if (candidate / "AGENTS.md").is_file():
            return candidate
    raise RuntimeError("找不到项目根目录：缺少 AGENTS.md")


DEFAULT_COVER_FONT_PATH = _project_root() / "static" / "font" / "MonuTitl-0.95CnBd.ttf"
DEFAULT_COVER_SIZE = "1920x1080"
# 抖音资料页会从横屏正中裁出 3:4 小图，标题必须落在该裁切区内。
DOUYIN_THUMB_ASPECT = 3 / 4
TITLE_INSET_X = 0.06
TITLE_INSET_TOP = 0.08
TITLE_INSET_BOTTOM = 0.22
TITLE_VERTICAL_BIAS = -0.12
MIN_FONT_SIZE = 42
MAX_FONT_SIZE = 150
LINE_SPACING = 0.18
# 黑描边固定 2～4px，取中间值。
STROKE_WIDTH = 3
TITLE_FILL_COLOR = (214, 168, 75)  # #D6A84B
TITLE_STROKE_COLOR = (0, 0, 0)
TITLE_SHADOW_COLOR = (0, 0, 0, 128)
TITLE_SHADOW_OFFSET_X = 4
TITLE_SHADOW_OFFSET_Y = 4
