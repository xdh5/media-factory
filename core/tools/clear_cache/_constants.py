"""清理缓存：工作流单次生产目录约定。"""

from pathlib import Path

_PROJECT_ROOT = Path(__file__).resolve().parents[3]
PROJECT_DATA_ROOT = _PROJECT_ROOT / "data"
PROJECT_CACHE_ROOT = _PROJECT_ROOT / "cache"
PROJECT_OUTPUT_ROOT = _PROJECT_ROOT / "outputs"
RUN_ID_PATTERN = r"^run-\d{6,}$"
WORKFLOW_ID_PATTERN = r"^[a-z][a-z0-9_]{0,63}$"
