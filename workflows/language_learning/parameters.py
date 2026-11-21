"""语言学习生产参数、运行目录和资源位置。"""

from tools.resources import package_resource_path
from tools.production_dates import (
    BEIJING_TIMEZONE as BEIJING_TIMEZONE,
    normalize_publish_date as normalize_publish_date,
    production_run_id as production_run_id,
    publish_date_from_run_id as publish_date_from_run_id,
)

from pathlib import Path

from tools.paths import (
    PROJECT_ROOT as PROJECT_ROOT,
    PROJECT_STATIC_ROOT,
    PROJECT_DATA_ROOT as PROJECT_DATA_ROOT,
    PROJECT_CACHE_ROOT as PROJECT_CACHE_ROOT,
    PROJECT_OUTPUT_ROOT as PROJECT_OUTPUT_ROOT,
    PROJECT_TMP_ROOT as PROJECT_TMP_ROOT,
)

WORKFLOW_ID = "language_learning"
SUPPORTED_LEARNING_MODES = ("en-zh", "en-ko")
SUPPORTED_VIDEO_FORMATS = ("standard", "quiz")
DEFAULT_VIDEO_FORMATS = ("standard", "quiz")
WORDS_PER_TASK = 10
WORD_HISTORY_DAYS = 100
MINIMUM_NEW_WORDS = (WORDS_PER_TASK + 1) // 2
CARD_CANVAS_SIZE = (1080, 1920)
SUBJECT_FRAME_ORIGIN = (335, 716)
SUBJECT_FRAME_SIZE = (410, 268)
CARD_GRID_COLUMNS = 5
CARD_GRID_ROWS = 2
QUIZ_POST_QUESTION_TRIM_SECONDS = 0.3
SUBJECT_SHEET_WIDTH = 1920
SUBJECT_SHEET_HEIGHT = 1080
SUBJECT_SHEET_SIZE = (SUBJECT_SHEET_WIDTH, SUBJECT_SHEET_HEIGHT)
SUBJECT_SHEET_RADIO = "16:9"
SUBJECT_SHEET_SIZE_TEXT = f"{SUBJECT_SHEET_WIDTH}x{SUBJECT_SHEET_HEIGHT}"
SUBJECT_SHEET_IMAGE_ID = "subject-sheet"
SUBJECT_ALPHA_THRESHOLD = 16
SUBJECT_CUTOUT_CACHE_DIR_NAME = "subject-cutouts"
SUBJECT_CUTOUT_STRATEGY_VERSION = "transparent-first-host-agent-boxes-v18"
SUBJECT_COMPONENT_MIN_RATIO = 0.03
SUBJECT_GENERATION_MAX_ATTEMPTS = 3
TOPIC_DEDUPLICATION_DAYS = 30
MAX_SUBJECT_SHEET_BYTES = 30 * 1024 * 1024
MAX_CARD_ARCHIVE_BYTES = 300 * 1024 * 1024
PUBLISH_MANIFEST_FILE_NAME = "publish-manifest.json"
TASKS_DIR_NAME = "tasks"

# 语言学习生产参数由 workflow 统一维护。
DEFAULT_PRODUCTION_CONFIG = {
    "learning_modes": ["en-zh", "en-ko"],
    "voices": {
        "en": "en-US-AriaNeural",
        "zh": "zh-CN-XiaoxiaoNeural",
        "ko": "ko-KR-SunHiNeural",
    },
    "language_pause": 0.3,
    "word_pause": 0.3,
    "video_formats": ["standard", "quiz"],
    "subject_generation_max_attempts": SUBJECT_GENERATION_MAX_ATTEMPTS,
    "publish_targets": ["youtube", "tiktok", "instagram", "facebook"],
}



DEFAULT_DATA_ROOT = PROJECT_DATA_ROOT / WORKFLOW_ID


def production_dirs(run_id: str) -> tuple[Path, Path]:
    """本次生产目录：(cache_dir, output_dir)。"""
    rid = str(run_id).strip()
    return PROJECT_CACHE_ROOT / WORKFLOW_ID / rid, PROJECT_OUTPUT_ROOT / WORKFLOW_ID / rid


def pack_cutout_cache_dir(pack_id: str) -> Path:
    """返回预制词包的主体切图验收缓存目录。"""
    value = str(pack_id or "").strip()
    return PROJECT_CACHE_ROOT / WORKFLOW_ID / "packs" / value / SUBJECT_CUTOUT_CACHE_DIR_NAME


# 卡片模板仍在本包 infrastructure/static/；倒计时音效统一放tools/static/sfx/
STATIC_ROOT = package_resource_path("workflows", "language_learning", "infrastructure", "static")
COUNTDOWN_AUDIO_PATH = PROJECT_STATIC_ROOT / "sfx" / "countdown.mp3"
TEMPLATE_FILENAMES = {
    "en-ko": "korean-fixed-vocabulary-template.jpg",
    "en-zh": "chinese-fixed-vocabulary-template.jpg",
}


def video_content_kind(learning_mode: str, video_format: str = "standard") -> str:
    """production_outputs.content_kind：原版为 en-zh / en-ko，问答版为 *-quiz。"""
    mode = str(learning_mode or "").strip()
    fmt = str(video_format or "standard").strip() or "standard"
    if fmt == "standard":
        return mode
    return f"{mode}-{fmt}"


def video_production_id(
    source: str,
    run_id: str,
    learning_mode: str,
    video_format: str,
    part: int,
) -> str:
    """幂等 production_id，问答版不得与原版第一段撞号。"""
    return (
        f"{source}:{WORKFLOW_ID}:{run_id}:"
        f"{video_content_kind(learning_mode, video_format)}:{int(part)}"
    )

# 成片标题、发布短标题与标签规则。
VIDEO_TITLE_TEMPLATES = {
    "en-zh": "10 Essential {topic} Words in Chinese",
    "en-ko": "韩语｜{first_word}的韩语怎么说？",
}
SHORT_TITLE_TEMPLATES = {"en-zh": "中文{topic}怎么说", "en-ko": "韩语单词怎么说"}
PUBLISH_TAGS = {
    "en-zh": ["#learnchinese", "#chinesevocabulary", "#mandarinchinese", "#dailychinese"],
    "en-ko": ["#学韩语", "#韩语单词", "#韩语入门", "#每日韩语"],
}
