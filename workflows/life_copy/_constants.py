"""人生文案工作流固定配置。改这条线时主要改本文件和 prompts、examples、static。"""

from pathlib import Path

WORKFLOW_ID = "life_copy"
TOPIC_DEDUPLICATION_DAYS = 30
VIDEO_SIZE = "1920x1080"
VIDEO_RADIO = "16:9"
COVER_FRAME_SECONDS = 1 / 30
# 画风：painterly（油画）/ realistic（写实）/ paper（纸艺）
VISUAL_STYLE = "painterly"
TTS_VOICE = "zh-CN-YunjianNeural"
TTS_RATE = "+20%"
TTS_TRIM_TRAILING_SILENCE = True
# BGM：cinematic_inspirational_piano / ambient_piano / ambient_techno
BGM_ID = "ambient_piano"
BGM_GAIN = 0.28
MIX_GAIN = 0.85
BGM_FADE_IN_SECONDS = 1.0
BGM_FADE_OUT_SECONDS = 2.0
# 必须和矩媒 GUI 里的账号组名完全一致
MATRIXMEDIA_ACCOUNT_GROUP = "人生文案"

_ROOT = Path(__file__).resolve().parent
ARTICLE_PROMPT_PATH = _ROOT / "prompts" / "article.md"
EXAMPLES_DIR = _ROOT / "examples"
HOOKS_PATH = EXAMPLES_DIR / "hooks.txt"
SHOT_IMAGE_RULES_PATH = _ROOT / "prompts" / "shot_image_rules.md"
REFERENCE_IMAGE_PATH = _ROOT / "static" / "ref_life_copy.png"
INTRO = "page_flip"
PAGE_FLIP_SFX_PATH = _ROOT / "static" / "page_flip.wav"
