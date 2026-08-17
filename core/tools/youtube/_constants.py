"""YouTube 发布工具常量。"""

from pathlib import Path

_PROJECT_ROOT = Path(__file__).resolve().parents[3]
YOUTUBE_TOKEN_DIR = _PROJECT_ROOT / "data" / "youtube" / "tokens"
YOUTUBE_SCOPES = [
    "https://www.googleapis.com/auth/youtube.upload",
    "https://www.googleapis.com/auth/youtube",
]
YOUTUBE_PRIVACY_STATUSES = ["private", "unlisted", "public"]
DEFAULT_CATEGORY_ID = "24"
DEFAULT_LANGUAGE = "zh"
UPLOAD_CHUNK_SIZE = 10 * 1024 * 1024
MAX_TRANSIENT_RETRIES = 8
