"""剪辑转文字工具常量。"""

from pathlib import Path

_PROJECT_ROOT = Path(__file__).resolve().parents[3]
DEFAULT_DATABASE_PATH = _PROJECT_ROOT / "data" / "media_factory.sqlite3"
JOB_NAMESPACE = "cliptext"
JOB_HANDLER = "core.tools.cliptext.transcribe:run_job"

GROQ_ASR_MODEL = "whisper-large-v3"
GROQ_ASR_BASE_URL = "https://api.groq.com/openai/v1"
GROQ_ASR_CHUNK_SECONDS = 1200
GROQ_CONNECT_TIMEOUT_SECONDS = 30
GROQ_READ_TIMEOUT_SECONDS = 1800
AUDIO_SAMPLE_RATE = 16_000
AUDIO_BITRATE = "64k"
SUPPORTED_LANGUAGES = ("zh", "en")