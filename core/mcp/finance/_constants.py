"""财经 MCP 技术常量（业务 Prompt 与参数见财经 Skill）。"""

import time
from pathlib import Path

MCP_ID = "finance"
DRAFT_FILE_NAME = "draft.json"
STORYBOARD_CONTEXT_FILE_NAME = "storyboard-context.json"
STORYBOARD_TEXT_FILE_NAME = "storyboard.txt"
TASKS_DIR_NAME = "tasks"

TOPIC_DEDUPLICATION_DAYS = 30
VIDEO_SIZE = "1920x1080"
VIDEO_RADIO = "16:9"

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
PROJECT_OUTPUT_ROOT = _PROJECT_ROOT / "outputs"
GENERATED_IMAGE_LIBRARY_ROOT = PROJECT_DATA_ROOT / "image_library" / "finance_generated"


def production_run_id(record_id: int | None = None) -> str:
    """生成不依赖数据库主键的数字 run_id；发布时才正式写入 D1。"""
    if record_id is not None:
        return f"run-{int(record_id):06d}"
    return f"run-{time.time_ns()}"


def production_dirs(run_id: str) -> tuple[Path, Path]:
    """本次生产目录：(cache_dir, output_dir)。"""
    rid = str(run_id).strip()
    return PROJECT_CACHE_ROOT / MCP_ID / rid, PROJECT_OUTPUT_ROOT / MCP_ID / rid
