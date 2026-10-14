"""收集财经文案的常量。"""

from pathlib import Path

PROJECT_ROOT = Path(__file__).resolve().parents[3]
CACHE_ROOT = PROJECT_ROOT / "cache" / "collect_finance_copy"
VIDEO_FILE_NAME = "video.mp4"
DIRECT_LINK_SOURCE = "direct_link"
COLLECTION_CODE_BY_NAME = {
    "财经": "finance",
}
