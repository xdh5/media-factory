"""抖音链接入库工具公开入口。"""

from ._errors import DouyinResearchError, IngestError
from .research import ingest_link

__all__ = ["ingest_link", "DouyinResearchError", "IngestError"]
