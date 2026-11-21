"""语音转文字错误。"""

from __future__ import annotations


class TranscriptionError(Exception):
    """转写工具错误基类。"""

    code = "TRANSCRIPTION_ERROR"

    def __init__(self, message: str, details: dict | None = None):
        super().__init__(message)
        self.message = message
        self.details = details or {}

    def to_dict(self) -> dict:
        return {"error": {"code": self.code, "message": self.message, "details": self.details}}


class InvalidParameterError(TranscriptionError):
    code = "INVALID_PARAMETER"

    def __init__(self, parameter: str, message: str):
        super().__init__(message, {"parameter": parameter})


class GroqConfigurationError(TranscriptionError):
    code = "GROQ_CONFIGURATION_ERROR"


class FFmpegNotFoundError(TranscriptionError):
    code = "FFMPEG_NOT_FOUND"

    def __init__(self) -> None:
        super().__init__("未找到 ffmpeg，请确认已安装并加入 PATH")
