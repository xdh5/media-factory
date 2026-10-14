"""导入 core 时把 media-collector 子仓库放进 Python 路径。"""

import sys
from pathlib import Path

_COLLECTOR_ROOT = Path(__file__).resolve().parents[1] / "integrations" / "media-collector"
if (_COLLECTOR_ROOT / "media_collector").is_dir():
    _collector = str(_COLLECTOR_ROOT)
    if _collector not in sys.path:
        sys.path.insert(0, _collector)
