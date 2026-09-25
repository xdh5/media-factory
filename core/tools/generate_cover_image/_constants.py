"""生成封面图片常量。"""

from pathlib import Path

def _project_root() -> Path:
    for candidate in Path(__file__).resolve().parents:
        if any((candidate / name).is_file() for name in ("AGENTS.md", "agents.md")):
            return candidate
    raise RuntimeError("找不到项目根目录：缺少 AGENTS.md 或 agents.md")


DEFAULT_COVER_FONT_PATH = _project_root() / "static" / "font" / "MechSong-DemiBold-2.ttf"
# 固定封面底图（2026-09-23 用户指定）：不再从镜头候选图随机抽，统一用这张。
DEFAULT_COVER_BACKGROUND_IMAGE = _project_root() / "static" / "cover" / "default-background.jpg"
DEFAULT_COVER_SIZE = "1920x1080"
# 抖音资料页会从横屏正中裁出 3:4 小图，标题必须落在该裁切区内。
DOUYIN_THUMB_ASPECT = 3 / 4
TITLE_INSET_X = 0.06
# 标题块放在画面下方 50%（top = 0.5 * 高度），底部仍留 0.22 安全边。
TITLE_INSET_TOP = 0.5
TITLE_INSET_BOTTOM = 0.22
TITLE_VERTICAL_BIAS = -0.12
MIN_FONT_SIZE = 42
MAX_FONT_SIZE = 150
LINE_SPACING = 0.18
# 参考财经账号封面使用较粗黑边，1080p 下取 6px。
STROKE_WIDTH = 6
TITLE_FILL_COLOR = (255, 255, 255)  # #FFFFFF
TITLE_HIGHLIGHT_COLOR = (242, 166, 35)  # #F2A623
TITLE_STROKE_COLOR = (0, 0, 0)
TITLE_SHADOW_COLOR = (0, 0, 0, 128)
TITLE_SHADOW_OFFSET_X = 4
TITLE_SHADOW_OFFSET_Y = 4
