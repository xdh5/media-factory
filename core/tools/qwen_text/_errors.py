"""千问文本生成错误定义。"""

from __future__ import annotations


class QwenTextError(Exception):
    """千问文本生成错误基类。"""

    code = "QWEN_TEXT_ERROR"

    def __init__(self, message: str, details: dict | None = None):
        super().__init__(message)
        self.message = message
        self.details = details or {}

    def to_dict(self) -> dict:
        return {"error": {"code": self.code, "message": self.message, "details": self.details}}


class QwenConfigurationError(QwenTextError):
    code = "QWEN_CONFIGURATION_ERROR"


class QwenRequestError(QwenTextError):
    code = "QWEN_REQUEST_ERROR"


class QwenResponseError(QwenTextError):
    code = "QWEN_RESPONSE_ERROR"
