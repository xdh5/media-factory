"""话题历史与去重工具公开入口。"""

from .topic_history import get_topic, update
from ._errors import DuplicateTopicError

__all__ = ["get_topic", "update", "DuplicateTopicError"]
