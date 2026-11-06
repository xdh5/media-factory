"""本地、容器和桌面运行时共用的项目目录。"""

from pathlib import Path

PROJECT_ROOT = Path(__file__).resolve().parent.parent
PROJECT_DATA_ROOT = PROJECT_ROOT / "data"
PROJECT_CACHE_ROOT = PROJECT_ROOT / "cache"
PROJECT_OUTPUT_ROOT = PROJECT_CACHE_ROOT / "output"
PROJECT_TMP_ROOT = PROJECT_CACHE_ROOT / "tmp"
PROJECT_STATIC_ROOT = PROJECT_ROOT / "core" / "static"
PROJECT_INTEGRATIONS_ROOT = PROJECT_ROOT / "integrations"
