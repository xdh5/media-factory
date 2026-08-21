"""话题去重公开入口。"""

from ._errors import DuplicateTopicError
from .topic_dedup import get_topic, update

__all__ = ["get_topic", "update", "DuplicateTopicError"]
