"""工作目录保存可写数据，安装包保存静态资源。"""

import os
from pathlib import Path

from .resources import package_resource_path

PROJECT_ROOT = Path(os.getenv("MEDIA_FACTORY_WORKSPACE", Path.cwd())).expanduser().resolve()
PROJECT_DATA_ROOT = PROJECT_ROOT / "data"
PROJECT_CACHE_ROOT = PROJECT_ROOT / "cache"
PROJECT_OUTPUT_ROOT = PROJECT_CACHE_ROOT / "output"
PROJECT_TMP_ROOT = PROJECT_CACHE_ROOT / "tmp"
PROJECT_STATIC_ROOT = package_resource_path("tools", "static")
PROJECT_INTEGRATIONS_ROOT = PROJECT_ROOT / "integrations"
