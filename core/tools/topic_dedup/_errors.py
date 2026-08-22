"""话题去重错误定义。"""

from __future__ import annotations


class TopicDedupError(Exception):
    code = "TOPIC_DEDUP_ERROR"

    def __init__(self, message: str, details: dict | None = None):
        super().__init__(message)
        self.message = message
        self.details = details or {}

    def to_dict(self) -> dict:
        return {"error": {"code": self.code, "message": self.message, "details": self.details}}


class InvalidParameterError(TopicDedupError):
    code = "INVALID_PARAMETER"

    def __init__(self, parameter: str, message: str):
        super().__init__(message, {"parameter": parameter})


class DuplicateTopicError(TopicDedupError):
    code = "DUPLICATE_TOPIC"


class TopicDataServiceError(TopicDedupError):
    code = "TOPIC_DATA_SERVICE_ERROR"
