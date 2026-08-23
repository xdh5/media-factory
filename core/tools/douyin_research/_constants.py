"""抖音研究工具常量。"""

from pathlib import Path

PROJECT_ROOT = Path(__file__).resolve().parents[3]
MEDIACRAWLER_ROOT = PROJECT_ROOT / "integrations" / "MediaCrawler"
MEDIACRAWLER_PYTHON = MEDIACRAWLER_ROOT / ".venv" / "Scripts" / "python.exe"
CACHE_ROOT = PROJECT_ROOT / "cache" / "douyin_research"
BRIDGE_PATH = Path(__file__).with_name("_mediacrawler_bridge.py")
CONTEXT_FILE_NAME = "context.json"
BRIDGE_INPUT_FILE_NAME = "crawler-input.json"
BRIDGE_OUTPUT_FILE_NAME = "crawler-output.json"
DEFAULT_LIMIT = 5
MAX_LIMIT = 5
SEARCH_POOL_SIZE = 30
CRAWLER_TIMEOUT_SECONDS = 1800
