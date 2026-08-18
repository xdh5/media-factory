"""财经工作流固定配置。"""

from pathlib import Path

WORKFLOW_ID = "finance"
TOPIC_DEDUPLICATION_DAYS = 30
VIDEO_SIZE = "1280x720"
VIDEO_RADIO = "16:9"
VISUAL_STYLE = "painterly"
TTS_VOICE = "zh-CN-YunxiNeural"
BGM_ID = "cinematic_inspirational_piano"
FINANCE_BGM_GAIN = 0.28
FINANCE_MIX_GAIN = 0.85
FINANCE_BGM_FADE_IN_SECONDS = 1.0
FINANCE_BGM_FADE_OUT_SECONDS = 2.0
DRAFT_FILE_NAME = "draft.json"
STORYBOARD_CONTEXT_FILE_NAME = "storyboard-context.json"
# 独立进程中调用的财经任务函数。
JOB_HANDLER = "workflows.finance.job_runner:run_job"
# 矩媒 GUI 里的账号组名，对应 list_accounts 返回的 phone 字段。
MATRIXMEDIA_ACCOUNT_GROUP = "心灵鸡汤"

_ROOT = Path(__file__).resolve().parent
_PROJECT_ROOT = _ROOT.parents[1]
PROJECT_DATA_ROOT = _PROJECT_ROOT / "data"
DEFAULT_DATA_ROOT = PROJECT_DATA_ROOT / WORKFLOW_ID
DEFAULT_DATABASE_PATH = PROJECT_DATA_ROOT / "media_factory.sqlite3"


def production_run_id(record_id: int) -> str:
    return f"run-{int(record_id):06d}"


def production_dirs(run_id: str) -> tuple[Path, Path, Path]:
    """本次生产目录：(run_dir, cache_dir, output_dir)。"""
    run_dir = PROJECT_DATA_ROOT / WORKFLOW_ID / "runs" / str(run_id).strip()
    return run_dir, run_dir / "cache", run_dir / "outputs"


FINANCE_PROMPT_PATH = _ROOT / "prompts" / "finance.md"
GLOBAL_PROMPT_ROOT = _PROJECT_ROOT / "core" / "prompts"
FORMAT_PROMPT_PATH = GLOBAL_PROMPT_ROOT / "format.md"
COVER_PROMPT_PATH = _ROOT / "prompts" / "cover.md"
TEXT2IMAGE_PROMPT_PATH = GLOBAL_PROMPT_ROOT / "text2image.md"
SHOT_IMAGE_RULES_PATH = _ROOT / "prompts" / "shot_image_rules.md"
FINANCE_REFERENCE_IMAGE_PATH = _ROOT / "static" / "ref_finance_people.png"
