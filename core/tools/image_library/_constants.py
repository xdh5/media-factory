"""财经等业务线图库约定。"""

from pathlib import Path

_PROJECT_ROOT = Path(__file__).resolve().parents[3]
PROJECT_ROOT = _PROJECT_ROOT
PROJECT_DATA_ROOT = _PROJECT_ROOT / "data"
DEFAULT_DATABASE_PATH = PROJECT_DATA_ROOT / "media_factory.sqlite3"
LINE_PATTERN = r"^[a-z][a-z0-9_]{0,63}$"
TOP_CANDIDATE_COUNT = 12
USAGE_WINDOW_MIN_DAYS = 21
