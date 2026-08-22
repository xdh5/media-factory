"""语言学习 MCP 技术常量（TTS、发布等业务参数见 SKILL）。"""

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
SUBJECT_CELL_WIDTH = SUBJECT_SHEET_WIDTH // CARD_GRID_COLUMNS
SUBJECT_CELL_HEIGHT = SUBJECT_SHEET_HEIGHT // CARD_GRID_ROWS
SUBJECT_ALPHA_THRESHOLD = 16
SUBJECT_REMBG_MODEL = "u2netp"
SUBJECT_CUTOUT_CACHE_DIR_NAME = "subject-cutouts"


def _subject_grid_box(index: int) -> tuple[int, int, int, int]:
    column = index % CARD_GRID_COLUMNS
    row = index // CARD_GRID_COLUMNS
    left = column * SUBJECT_CELL_WIDTH
    top = row * SUBJECT_CELL_HEIGHT
    return (left, top, left + SUBJECT_CELL_WIDTH, top + SUBJECT_CELL_HEIGHT)


SUBJECT_GRID_BOXES = tuple(_subject_grid_box(index) for index in range(WORDS_PER_TASK))
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
        if (candidate / "AGENTS.md").is_file():
            return candidate
    raise RuntimeError("找不到项目根目录：缺少 AGENTS.md")


PROJECT_ROOT = _project_root()
PROJECT_DATA_ROOT = PROJECT_ROOT / "data"
PROJECT_CACHE_ROOT = PROJECT_ROOT / "cache"
PROJECT_OUTPUT_ROOT = PROJECT_ROOT / "outputs"
DEFAULT_DATA_ROOT = PROJECT_DATA_ROOT / WORKFLOW_ID


def production_run_id(record_id: int) -> str:
    return f"run-{int(record_id):06d}"


def production_dirs(run_id: str) -> tuple[Path, Path]:
    """本次生产目录：(cache_dir, output_dir)。"""
    rid = str(run_id).strip()
    return PROJECT_CACHE_ROOT / WORKFLOW_ID / rid, PROJECT_OUTPUT_ROOT / WORKFLOW_ID / rid


STATIC_ROOT = _ROOT / "static"
TEMPLATE_FILENAMES = {
    "en-ko": "korean-fixed-vocabulary-template.jpg",
    "en-zh": "chinese-fixed-vocabulary-template.jpg",
}
