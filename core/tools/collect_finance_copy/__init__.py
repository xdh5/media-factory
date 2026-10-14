"""收集财经文案的公开入口。"""

from ._errors import CollectCopyError, CollectFinanceCopyError
from .collect import collect_copy

__all__ = ["collect_copy", "CollectCopyError", "CollectFinanceCopyError"]
