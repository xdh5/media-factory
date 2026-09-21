"""心灵鸡汤 MCP 技术常量。"""

from datetime import date, datetime
from pathlib import Path
from zoneinfo import ZoneInfo

MCP_ID = "psychology_quiz"
DRAFT_FILE_NAME = "draft.json"
STORYBOARD_CONTEXT_FILE_NAME = "storyboard-context.json"
STORYBOARD_TEXT_FILE_NAME = "storyboard.txt"
TOPIC_DEDUPLICATION_DAYS = 30
VIDEO_SIZE = "1920x1080"
VIDEO_RADIO = "16:9"
MATRIXMEDIA_AI_CREATIVE_STATEMENT = "ai_generated"

_ROOT = Path(__file__).resolve().parent
QUIZ_PROMPT_PATH = _ROOT / "prompts" / "quiz.md"
METADATA_PROMPT_PATH = _ROOT / "prompts" / "metadata.md"
STORYBOARD_PROMPT_PATH = _ROOT / "prompts" / "storyboard.md"
BEIJING_TIMEZONE = ZoneInfo("Asia/Shanghai")


def _project_root() -> Path:
    for candidate in Path(__file__).resolve().parents:
        if any((candidate / name).is_file() for name in ("AGENTS.md", "agents.md")):
            return candidate
    raise RuntimeError("找不到项目根目录：缺少 AGENTS.md 或 agents.md")


PROJECT_ROOT = _project_root()
PROJECT_CACHE_ROOT = PROJECT_ROOT / "cache"
PROJECT_OUTPUT_ROOT = PROJECT_ROOT / "output"


def normalize_publish_date(publish_date: str) -> str:
    """校验北京时间计划发布日期，返回 YYYY-MM-DD。"""
    value = str(publish_date or "").strip()
    try:
        resolved = date.fromisoformat(value)
    except ValueError as exc:
        raise ValueError("publish_date 必须是 YYYY-MM-DD") from exc
    today = datetime.now(BEIJING_TIMEZONE).date()
    if resolved < today:
        raise ValueError(f"publish_date 不能早于北京时间今天 {today.isoformat()}")
    return resolved.isoformat()


def production_run_id(publish_date: str) -> str:
    return f"run-{normalize_publish_date(publish_date).replace('-', '')}"


def publish_date_from_run_id(run_id: str) -> str:
    value = str(run_id or "").strip()
    if not value.startswith("run-") or len(value) != 12 or not value[4:].isdigit():
        raise ValueError("run_id 必须是 run-YYYYMMDD")
    return date.fromisoformat(f"{value[4:8]}-{value[8:10]}-{value[10:12]}").isoformat()


def production_dirs(run_id: str) -> tuple[Path, Path]:
    return (
        (PROJECT_CACHE_ROOT / MCP_ID / run_id).resolve(),
        (PROJECT_OUTPUT_ROOT / MCP_ID / run_id).resolve(),
    )
