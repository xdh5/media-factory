"""千问视觉理解错误定义。"""

from __future__ import annotations


class QwenVisionError(Exception):
    """千问视觉理解错误基类。"""

    code = "QWEN_VISION_ERROR"

    def __init__(self, message: str, details: dict | None = None):
        super().__init__(message)
        self.message = message
        self.details = details or {}

    def to_dict(self) -> dict:
        return {"error": {"code": self.code, "message": self.message, "details": self.details}}


class QwenVisionConfigurationError(QwenVisionError):
    code = "QWEN_VISION_CONFIGURATION_ERROR"


class QwenVisionRequestError(QwenVisionError):
    code = "QWEN_VISION_REQUEST_ERROR"


class QwenVisionResponseError(QwenVisionError):
    code = "QWEN_VISION_RESPONSE_ERROR"
