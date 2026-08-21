"""生成封面图片错误定义。"""

from __future__ import annotations


class CoverError(Exception):
    code = "COVER_ERROR"

    def __init__(self, message: str, details: dict | None = None):
        super().__init__(message)
        self.message = message
        self.details = details or {}

    def to_dict(self) -> dict:
        return {"error": {"code": self.code, "message": self.message, "details": self.details}}


class InvalidParameterError(CoverError):
    code = "INVALID_PARAMETER"

    def __init__(self, parameter: str, message: str):
        super().__init__(message, {"parameter": parameter})


class CoverSourceImageError(CoverError):
    code = "COVER_SOURCE_IMAGE_ERROR"


class CoverFontError(CoverError):
    code = "COVER_FONT_ERROR"


class CoverRenderError(CoverError):
    code = "COVER_RENDER_ERROR"
