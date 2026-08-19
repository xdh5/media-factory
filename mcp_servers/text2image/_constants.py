"""文生图 MCP 常量。"""

from pathlib import Path

MCP_ID = "text2image"
JOB_HANDLER = "mcp_servers.text2image.job_runner:run_job"
DRAFT_FILE_NAME = "draft.json"
STORYBOARD_CONTEXT_FILE_NAME = "storyboard-context.json"
STORYBOARD_TEXT_FILE_NAME = "storyboard.txt"

_ROOT = Path(__file__).resolve().parent


def _project_root() -> Path:
    for candidate in Path(__file__).resolve().parents:
        if (candidate / "core" / "prompts" / "format.md").is_file():
            return candidate
    raise RuntimeError("找不到项目根目录：缺少 core/prompts/format.md")


_PROJECT_ROOT = _project_root()
PROJECT_DATA_ROOT = _PROJECT_ROOT / "data"
DEFAULT_DATABASE_PATH = PROJECT_DATA_ROOT / "media_factory.sqlite3"
GLOBAL_PROMPT_ROOT = _PROJECT_ROOT / "core" / "prompts"
FORMAT_PROMPT_PATH = GLOBAL_PROMPT_ROOT / "format.md"
TEXT2IMAGE_PROMPT_PATH = GLOBAL_PROMPT_ROOT / "text2image.md"


def production_run_id(record_id: int) -> str:
    return f"run-{int(record_id):06d}"


def production_dirs(line_id: str, run_id: str) -> tuple[Path, Path, Path]:
    """本次生产目录：(run_dir, cache_dir, output_dir)。"""
    run_dir = PROJECT_DATA_ROOT / str(line_id).strip() / "runs" / str(run_id).strip()
    return run_dir, run_dir / "cache", run_dir / "outputs"
