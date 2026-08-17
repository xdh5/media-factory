"""财经工作流固定配置。"""

from pathlib import Path

WORKFLOW_ID = "finance"
TOPIC_DEDUPLICATION_DAYS = 30
VIDEO_SIZE = "1920x1080"
VIDEO_RADIO = "16:9"
VISUAL_STYLE = "painterly"
TTS_VOICE = "zh-CN-YunxiNeural"
BGM_ID = "cinematic_inspirational_piano"
DEFAULT_PUBLISH_ACCOUNT_GROUP = "心灵鸡汤"
DRAFT_FILE_NAME = "draft.json"
STORYBOARD_CONTEXT_FILE_NAME = "storyboard-context.json"

_ROOT = Path(__file__).resolve().parent
_PROJECT_ROOT = _ROOT.parents[2]
PROJECT_DATA_ROOT = _PROJECT_ROOT / "data"
DEFAULT_DATA_ROOT = PROJECT_DATA_ROOT / WORKFLOW_ID
DEFAULT_DATABASE_PATH = PROJECT_DATA_ROOT / "media_factory.sqlite3"
DEFAULT_CACHE_ROOT = DEFAULT_DATA_ROOT / "cache"
DEFAULT_OUTPUT_ROOT = DEFAULT_DATA_ROOT / "outputs"
FINANCE_PROMPT_PATH = _ROOT / "prompts" / "finance.md"
GLOBAL_PROMPT_ROOT = _ROOT.parent.parent / "prompts"
FORMAT_PROMPT_PATH = GLOBAL_PROMPT_ROOT / "format.md"
COVER_PROMPT_PATH = GLOBAL_PROMPT_ROOT / "cover.md"
TEXT2IMAGE_PROMPT_PATH = GLOBAL_PROMPT_ROOT / "text2image.md"
