"""财经工作流固定配置。"""

from pathlib import Path

WORKFLOW_ID = "finance"
TOPIC_DEDUPLICATION_DAYS = 30
VIDEO_SIZE = "1920x1080"
VIDEO_RADIO = "16:9"
COVER_FRAME_SECONDS = 1 / 30
VISUAL_STYLE = "painterly"
TTS_VOICE = "zh-CN-YunjianNeural"
TTS_RATE = "+20%"
TTS_TRIM_TRAILING_SILENCE = True
BGM_ID = "cinematic_inspirational_piano"
FINANCE_BGM_GAIN = 0.28
FINANCE_MIX_GAIN = 0.85
FINANCE_BGM_FADE_IN_SECONDS = 1.0
FINANCE_BGM_FADE_OUT_SECONDS = 2.0
MATRIXMEDIA_ACCOUNT_GROUP = "心灵鸡汤"

_ROOT = Path(__file__).resolve().parent
FINANCE_PROMPT_PATH = _ROOT / "prompts" / "finance.md"
FINANCE_EXAMPLES_DIR = _ROOT / "examples"
FINANCE_HOOKS_PATH = FINANCE_EXAMPLES_DIR / "hooks.txt"
SHOT_IMAGE_RULES_PATH = _ROOT / "prompts" / "shot_image_rules.md"
FINANCE_REFERENCE_IMAGE_PATH = _ROOT / "static" / "ref_finance_people.png"
