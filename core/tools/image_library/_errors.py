"""图库工具错误定义。"""

from __future__ import annotations


class ImageLibraryError(Exception):
    code = "IMAGE_LIBRARY_ERROR"

    def __init__(self, message: str, details: dict | None = None):
        super().__init__(message)
        self.message = message
        self.details = details or {}

    def to_dict(self) -> dict:
        return {"error": {"code": self.code, "message": self.message, "details": self.details}}


class InvalidParameterError(ImageLibraryError):
    code = "INVALID_PARAMETER"

    def __init__(self, parameter: str, message: str):
        super().__init__(message, {"parameter": parameter})


class ImageLibraryDatabaseError(ImageLibraryError):
    code = "IMAGE_LIBRARY_DATABASE_ERROR"


class ImageLibraryEmptyError(ImageLibraryError):
    code = "IMAGE_LIBRARY_EMPTY"
