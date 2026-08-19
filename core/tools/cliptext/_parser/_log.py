"""解析器内部日志，替代旧项目 src.core.logging。"""

from __future__ import annotations

import logging

logger = logging.getLogger("cliptext.parser")
if not logger.handlers:
    handler = logging.StreamHandler()
    handler.setFormatter(logging.Formatter("%(levelname)s %(name)s: %(message)s"))
    logger.addHandler(handler)
    logger.setLevel(logging.INFO)
