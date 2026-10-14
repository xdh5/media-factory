"""工厂侧下载入口。实现在 integrations/media-collector。"""

import sys
from pathlib import Path

_PACKAGE_ROOT = Path(__file__).resolve().parents[3] / "integrations" / "media-collector"
if not (_PACKAGE_ROOT / "media_collector").is_dir():
    raise ImportError(
        "未找到 media-collector。请在仓库根目录执行："
        "git submodule update --init integrations/media-collector"
    )
_root = str(_PACKAGE_ROOT)
if _root not in sys.path:
    sys.path.insert(0, _root)

from media_collector import DownloadError, download

__all__ = ["DownloadError", "download"]
