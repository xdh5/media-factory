"""语言学习 MCP 技术常量（TTS、发布等业务参数见 SKILL）。"""

from datetime import date, datetime
from pathlib import Path
from zoneinfo import ZoneInfo

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
MATRIXMEDIA_AI_CREATIVE_STATEMENT = "ai_generated"
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
PROJECT_OUTPUT_ROOT = PROJECT_ROOT / "output"
DEFAULT_DATA_ROOT = PROJECT_DATA_ROOT / WORKFLOW_ID
BEIJING_TIMEZONE = ZoneInfo("Asia/Shanghai")


def normalize_publish_date(publish_date: str) -> str:
    """校验北京时间计划发布日期，返回 YYYY-MM-DD。"""
    value = str(publish_date or "").strip()
    try:
        resolved = date.fromisoformat(value)
    except ValueError as exc:
        raise ValueError("publish_date 必须是 YYYY-MM-DD，例如 2026-08-25") from exc
    today = datetime.now(BEIJING_TIMEZONE).date()
    if resolved < today:
        raise ValueError(f"publish_date 不能早于北京时间当天 {today.isoformat()}")
    return resolved.isoformat()


def production_run_id(publish_date: str) -> str:
    """按北京时间计划发布日期生成 run-YYYYMMDD。"""
    normalized = normalize_publish_date(publish_date)
    return f"run-{normalized.replace('-', '')}"


def publish_date_from_run_id(run_id: str) -> str:
    """从新格式 run-YYYYMMDD 还原北京时间计划发布日期。"""
    value = str(run_id or "").strip()
    if len(value) != 12 or not value.startswith("run-") or not value[4:].isdigit():
        raise ValueError("run_id 必须是 run-YYYYMMDD，例如 run-20260825")
    raw = value[4:]
    try:
        return date(int(raw[:4]), int(raw[4:6]), int(raw[6:8])).isoformat()
    except ValueError as exc:
        raise ValueError(f"run_id 包含无效日期：{value}") from exc


def production_dirs(run_id: str) -> tuple[Path, Path]:
    """本次生产目录：(cache_dir, output_dir)。"""
    rid = str(run_id).strip()
    return PROJECT_CACHE_ROOT / WORKFLOW_ID / rid, PROJECT_OUTPUT_ROOT / WORKFLOW_ID / rid


STATIC_ROOT = _ROOT / "static"
TEMPLATE_FILENAMES = {
    "en-ko": "korean-fixed-vocabulary-template.jpg",
    "en-zh": "chinese-fixed-vocabulary-template.jpg",
}
