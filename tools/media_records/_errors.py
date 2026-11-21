"""媒体生产记录错误定义。"""

from __future__ import annotations


class MediaRecordsError(Exception):
    """媒体生产记录错误基类。"""

    code = "MEDIA_RECORDS_ERROR"

    def __init__(self, message: str, details: dict | None = None):
        super().__init__(message)
        self.message = message
        self.details = details or {}

    def to_dict(self) -> dict:
        return {"error": {"code": self.code, "message": self.message, "details": self.details}}


class MediaRecordsConfigurationError(MediaRecordsError):
    code = "MEDIA_RECORDS_CONFIGURATION_ERROR"


class MediaRecordsRequestError(MediaRecordsError):
    code = "MEDIA_RECORDS_REQUEST_ERROR"


class MediaRecordsConflictError(MediaRecordsError):
    code = "MEDIA_RECORDS_CONFLICT"

    def __init__(self, message: str, details: dict | None = None, *, remote_code: str = "CONFLICT"):
        super().__init__(message, details)
        self.remote_code = remote_code

