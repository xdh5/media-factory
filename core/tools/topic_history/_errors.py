"""话题历史工具错误定义。"""

from __future__ import annotations


class TopicHistoryError(Exception):
    code = "TOPIC_HISTORY_ERROR"

    def __init__(self, message: str, details: dict | None = None):
        super().__init__(message)
        self.message = message
        self.details = details or {}

    def to_dict(self) -> dict:
        return {"error": {"code": self.code, "message": self.message, "details": self.details}}


class InvalidParameterError(TopicHistoryError):
    code = "INVALID_PARAMETER"

    def __init__(self, parameter: str, message: str):
        super().__init__(message, {"parameter": parameter})


class DuplicateTopicError(TopicHistoryError):
    code = "DUPLICATE_TOPIC"


class TopicRecordNotFoundError(TopicHistoryError):
    code = "TOPIC_RECORD_NOT_FOUND"


class TopicDatabaseError(TopicHistoryError):
    code = "TOPIC_DATABASE_ERROR"
