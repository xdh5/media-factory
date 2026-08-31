"""财经 MCP 技术常量（业务 Prompt 与参数见财经 Skill）。"""

from datetime import date, datetime
from pathlib import Path
from zoneinfo import ZoneInfo

MCP_ID = "finance"
SOURCE_COLLECTION_CODE = "finance"
SOURCE_RESERVATION_MINUTES = 120
DRAFT_FILE_NAME = "draft.json"
STORYBOARD_CONTEXT_FILE_NAME = "storyboard-context.json"
STORYBOARD_TEXT_FILE_NAME = "storyboard.txt"
TASKS_DIR_NAME = "tasks"

TOPIC_DEDUPLICATION_DAYS = 30
VIDEO_SIZE = "1920x1080"
VIDEO_RADIO = "16:9"
MATRIXMEDIA_AI_CREATIVE_STATEMENT = "ai_generated"
ARTICLE_MIN_LENGTH = 450
ARTICLE_MAX_LENGTH = 550

_ROOT = Path(__file__).resolve().parent
METADATA_PROMPT_PATH = _ROOT / "prompts" / "metadata.md"
SHOT_IMAGE_RULES_PATH = _ROOT / "prompts" / "shot_image_rules.md"


def _project_root() -> Path:
    for candidate in Path(__file__).resolve().parents:
        if any((candidate / name).is_file() for name in ("AGENTS.md", "agents.md")):
            return candidate
    raise RuntimeError("找不到项目根目录：缺少 AGENTS.md 或 agents.md")


_PROJECT_ROOT = _project_root()
PROJECT_DATA_ROOT = _PROJECT_ROOT / "data"
PROJECT_CACHE_ROOT = _PROJECT_ROOT / "cache"
PROJECT_OUTPUT_ROOT = _PROJECT_ROOT / "output"
GENERATED_IMAGE_LIBRARY_ROOT = PROJECT_DATA_ROOT / "image_library_finance"
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
    return PROJECT_CACHE_ROOT / MCP_ID / rid, PROJECT_OUTPUT_ROOT / MCP_ID / rid
