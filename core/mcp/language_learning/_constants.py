"""语言学习 MCP 技术常量（TTS、发布等业务参数见 SKILL）。"""

import time
from pathlib import Path

WORKFLOW_ID = "language_learning"
SUPPORTED_LEARNING_MODES = ("en-zh", "en-ko")
WORDS_PER_VIDEO = 5
WORDS_PER_TASK = 10
WORD_HISTORY_DAYS = 100
MINIMUM_NEW_WORDS = (WORDS_PER_TASK + 1) // 2
CARD_CANVAS_SIZE = (1080, 1920)
CARD_GRID_COLUMNS = 5
CARD_GRID_ROWS = 2
SUBJECT_SHEET_WIDTH = 1920
SUBJECT_SHEET_HEIGHT = 1080
SUBJECT_SHEET_SIZE = (SUBJECT_SHEET_WIDTH, SUBJECT_SHEET_HEIGHT)
SUBJECT_SHEET_RADIO = "16:9"
SUBJECT_SHEET_SIZE_TEXT = f"{SUBJECT_SHEET_WIDTH}x{SUBJECT_SHEET_HEIGHT}"
SUBJECT_SHEET_IMAGE_ID = "subject-sheet"
SUBJECT_ALPHA_THRESHOLD = 16
SUBJECT_CHROMA_LOW_DISTANCE = 18
SUBJECT_CHROMA_HIGH_DISTANCE = 64
SUBJECT_CUTOUT_CACHE_DIR_NAME = "subject-cutouts"
SUBJECT_CUTOUT_STRATEGY_VERSION = "host-agent-conservative-boxes-v13"
SUBJECT_GENERATION_MAX_ATTEMPTS = 3
TOPIC_DEDUPLICATION_DAYS = 30
MAX_SUBJECT_SHEET_BYTES = 30 * 1024 * 1024
MAX_CARD_ARCHIVE_BYTES = 300 * 1024 * 1024
CHINESE_YOUTUBE_CHANNEL_ID = "UC2WPS9jGyQF38pzj_j2EA5g"
YOUTUBE_LANGUAGE_LEARNING_CATEGORY_ID = "27"
YOUTUBE_LANGUAGE_BY_MODE = {"en-zh": "zh", "en-ko": "ko"}
PUBLISH_MANIFEST_FILE_NAME = "publish-manifest.json"
TASKS_DIR_NAME = "tasks"

_ROOT = Path(__file__).resolve().parent


def _project_root() -> Path:
    for candidate in Path(__file__).resolve().parents:
        if any((candidate / name).is_file() for name in ("AGENTS.md", "agents.md")):
            return candidate
    raise RuntimeError("找不到项目根目录：缺少 AGENTS.md 或 agents.md")


PROJECT_ROOT = _project_root()
PROJECT_DATA_ROOT = PROJECT_ROOT / "data"
PROJECT_CACHE_ROOT = PROJECT_ROOT / "cache"
PROJECT_OUTPUT_ROOT = PROJECT_ROOT / "outputs"
DEFAULT_DATA_ROOT = PROJECT_DATA_ROOT / WORKFLOW_ID


def production_run_id(record_id: int | None = None) -> str:
    """生成不依赖数据库主键的数字 run_id；发布时才正式写入 D1。"""
    if record_id is not None:
        return f"run-{int(record_id):06d}"
    return f"run-{time.time_ns()}"


def production_dirs(run_id: str) -> tuple[Path, Path]:
    """本次生产目录：(cache_dir, output_dir)。"""
    rid = str(run_id).strip()
    return PROJECT_CACHE_ROOT / WORKFLOW_ID / rid, PROJECT_OUTPUT_ROOT / WORKFLOW_ID / rid


STATIC_ROOT = _ROOT / "static"
TEMPLATE_FILENAMES = {
    "en-ko": "korean-fixed-vocabulary-template.jpg",
    "en-zh": "chinese-fixed-vocabulary-template.jpg",
}
