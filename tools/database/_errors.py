"""公共数据 API 错误定义。"""

from __future__ import annotations


class DatabaseError(Exception):
    """公共数据 API 错误基类。"""

    code = "DATABASE_ERROR"

    def __init__(self, message: str, details: dict | None = None):
        super().__init__(message)
        self.message = message
        self.details = details or {}

    def to_dict(self) -> dict:
        return {"error": {"code": self.code, "message": self.message, "details": self.details}}


class DatabaseConfigurationError(DatabaseError):
    code = "DATABASE_CONFIGURATION_ERROR"


class DatabaseRequestError(DatabaseError):
    code = "DATABASE_REQUEST_ERROR"


class DatabaseConflictError(DatabaseError):
    code = "DATABASE_CONFLICT"

    def __init__(self, message: str, details: dict | None = None, *, remote_code: str = "CONFLICT"):
        super().__init__(message, details)
        self.remote_code = remote_code



class TopicHistoryError(DatabaseError):
    """话题历史操作错误。"""
    code = "TOPIC_HISTORY_ERROR"


class TopicParameterError(TopicHistoryError):
    code = "INVALID_PARAMETER"

    def __init__(self, parameter: str, message: str):
        super().__init__(message, {"parameter": parameter})


class DuplicateTopicError(TopicHistoryError):
    code = "DUPLICATE_TOPIC"
