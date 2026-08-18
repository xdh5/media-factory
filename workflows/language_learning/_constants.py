"""语言学习工作流固定配置。"""

from pathlib import Path

WORKFLOW_ID = "language_learning"
SUPPORTED_LEARNING_MODES = ("en-zh", "en-ko")
WORDS_PER_VIDEO = 5
WORDS_PER_TASK = 10
CARD_CANVAS_SIZE = (1080, 1920)
CARD_GRID_COLUMNS = 5
CARD_GRID_ROWS = 2
SUBJECT_SHEET_WIDTH = 1920
SUBJECT_SHEET_HEIGHT = 1080
SUBJECT_SHEET_SIZE = (SUBJECT_SHEET_WIDTH, SUBJECT_SHEET_HEIGHT)
SUBJECT_SHEET_RADIO = "16:9"
SUBJECT_SHEET_SIZE_TEXT = f"{SUBJECT_SHEET_WIDTH}x{SUBJECT_SHEET_HEIGHT}"
SUBJECT_SHEET_IMAGE_ID = "subject-sheet"
SUBJECT_SHEET_ASPECT_MAX_PIXEL_ERROR = 1
SUBJECT_CELL_WIDTH = SUBJECT_SHEET_WIDTH // CARD_GRID_COLUMNS
SUBJECT_CELL_HEIGHT = SUBJECT_SHEET_HEIGHT // CARD_GRID_ROWS
SUBJECT_ALPHA_THRESHOLD = 16


def _subject_grid_box(index: int) -> tuple[int, int, int, int]:
    column = index % CARD_GRID_COLUMNS
    row = index // CARD_GRID_COLUMNS
    left = column * SUBJECT_CELL_WIDTH
    top = row * SUBJECT_CELL_HEIGHT
    return (left, top, left + SUBJECT_CELL_WIDTH, top + SUBJECT_CELL_HEIGHT)


SUBJECT_GRID_BOXES = tuple(_subject_grid_box(index) for index in range(WORDS_PER_TASK))
DEFAULT_LANGUAGE_PAUSE = 0.3
DEFAULT_WORD_PAUSE = 0.3
TOPIC_DEDUPLICATION_DAYS = 30
MAX_SUBJECT_SHEET_BYTES = 30 * 1024 * 1024
MAX_CARD_ARCHIVE_BYTES = 300 * 1024 * 1024
CHINESE_PUBLISH_ACCOUNT_GROUP = "学中文"
CHINESE_PUBLISH_TAGS = ["#learnchinese", "#chinesevocabulary", "#mandarinchinese", "#dailychinese"]
YOUTUBE_LANGUAGE_LEARNING_CATEGORY_ID = "27"
YOUTUBE_LANGUAGE_BY_MODE = {"en-zh": "zh", "en-ko": "ko"}
PUBLISH_MANIFEST_FILE_NAME = "publish-manifest.json"
JOB_HANDLER = "workflows.language_learning.job_runner:run_job"

_ROOT = Path(__file__).resolve().parent
PROJECT_ROOT = _ROOT.parents[1]
PROJECT_DATA_ROOT = PROJECT_ROOT / "data"
DEFAULT_DATA_ROOT = PROJECT_DATA_ROOT / WORKFLOW_ID
DEFAULT_DATABASE_PATH = PROJECT_DATA_ROOT / "media_factory.sqlite3"


def production_run_id(record_id: int) -> str:
    return f"run-{int(record_id):06d}"


def production_dirs(run_id: str) -> tuple[Path, Path, Path]:
    """本次生产目录：(run_dir, cache_dir, output_dir)。"""
    run_dir = PROJECT_DATA_ROOT / WORKFLOW_ID / "runs" / str(run_id).strip()
    return run_dir, run_dir / "cache", run_dir / "outputs"


PROMPT_ROOT = _ROOT / "prompts"
STATIC_ROOT = _ROOT / "static"
TEMPLATE_FILENAMES = {
    "en-ko": "korean-fixed-vocabulary-template.jpg",
    "en-zh": "chinese-fixed-vocabulary-template.jpg",
}
VOICE_BY_LANGUAGE = {
    "en": "en-US-AriaNeural",
    "zh": "zh-CN-XiaoxiaoNeural",
    "ko": "ko-KR-SunHiNeural",
}
