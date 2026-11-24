"""财经生产参数、运行目录和资源位置。"""

from tools.resources import package_resource_path
from tools.paths import PROJECT_STATIC_ROOT
from tools.production_dates import (
    BEIJING_TIMEZONE as BEIJING_TIMEZONE,
    normalize_publish_date as normalize_publish_date,
    production_run_id as production_run_id,
    publish_date_from_run_id as publish_date_from_run_id,
)

from pathlib import Path

from tools.paths import (
    PROJECT_DATA_ROOT as PROJECT_DATA_ROOT,
    PROJECT_CACHE_ROOT as PROJECT_CACHE_ROOT,
    PROJECT_OUTPUT_ROOT as PROJECT_OUTPUT_ROOT,
    PROJECT_TMP_ROOT as PROJECT_TMP_ROOT,
)

MCP_ID = "finance"
SOURCE_COLLECTION_CODE = "finance"
SOURCE_RESERVATION_MINUTES = 120
DRAFT_FILE_NAME = "draft.json"
STORYBOARD_CONTEXT_FILE_NAME = "storyboard-context.json"
STORYBOARD_TEXT_FILE_NAME = "storyboard.txt"

TOPIC_DEDUPLICATION_DAYS = 30
VIDEO_SIZE = "1920x1080"
VIDEO_RADIO = "16:9"
ENDING_VIDEO_PATH = package_resource_path("workflows", "finance", "resources", "goose-outro.mp4")
# 缩放变化 10%，平移使用 12% 放大的完整裁切余量。
IMAGE_MOTION_EFFECTS = (
    {"name": "缓慢放大", "zoom_from": 1.00, "zoom_to": 1.10},
    {"name": "缓慢缩小", "zoom_from": 1.10, "zoom_to": 1.00},
    {"name": "从上向下", "zoom_from": 1.12, "zoom_to": 1.12, "pan_from_y": 0.0, "pan_to_y": 1.0},
    {"name": "从下向上", "zoom_from": 1.12, "zoom_to": 1.12, "pan_from_y": 1.0, "pan_to_y": 0.0},
)
CONTENT_KIND = "finance"
AUTOMATION_DAILY_OUTPUT_COUNT = 2

# 正文在两类必做改动（品牌替换、连载指涉改写）之外允许措辞级改写。
# 原稿入库前已补标点并修正错别字，制作时视为文字和标点正确。
# 但大结构与信息量必须与原稿一致；
# 正文每行对应一个分镜，字幕显示层按词边界换行。
ARTICLE_MAX_LINE_LENGTH = 60

# 财经生产使用正版实拍视频。
MATERIAL_STOCK_VIDEO = "stock_video"
MATERIAL_STRATEGIES = (MATERIAL_STOCK_VIDEO,)

# 财经生产参数由 workflow 统一维护。
DEFAULT_PRODUCTION_CONFIG = {
    "material_strategy": MATERIAL_STOCK_VIDEO,
    "tts_config": {
        "voice": "azure:zh-CN-YunyiMultilingualNeural",
        "rate": "+20%",
    },
    "video_config": {
        "orientation": "landscape",
        "per_provider": 8,
        "soft_blur_sigma": 0.55,
    },
    "production_config": {
        "bgm_path": "tools/static/bgm/easy-lemon-kevin-macleod.mp3",
        "bgm_gain": 0.0504,
        "intro": "slide_in_shutter",
        "shot_stickers": ["rec"],
    },
}



COLLECTION_CACHE_ROOT = PROJECT_CACHE_ROOT / "collect_finance_copy"


def production_dirs(run_id: str, content_part: int = 1) -> tuple[Path, Path]:
    """本次生产目录：(cache_dir, output_dir)。

    同一天第二条及以后（content_part >= 2）使用 run-YYYYMMDD-partN 后缀目录；
    run_id 本身保持 run-YYYYMMDD，供 D1 唯一键 (run_id, content_part) 使用。
    """
    rid = str(run_id).strip()
    part = int(content_part or 1)
    suffix = "" if part <= 1 else f"-part{part}"
    return (
        PROJECT_CACHE_ROOT / MCP_ID / f"{rid}{suffix}",
        PROJECT_OUTPUT_ROOT / MCP_ID / f"{rid}{suffix}",
    )

# 财经封面排版参数。
DEFAULT_COVER_FONT_PATH = PROJECT_STATIC_ROOT / "font" / "MechSong-DemiBold-2.ttf"
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
