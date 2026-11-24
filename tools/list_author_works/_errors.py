"""获取作者作品列表的错误。"""

from __future__ import annotations


class AuthorWorksError(Exception):
    """作者作品列表错误基类。"""

    code = "AUTHOR_WORKS_ERROR"

    def __init__(self, message: str, details: dict | None = None):
        super().__init__(message)
        self.message = message
        self.details = details or {}

    def to_dict(self) -> dict:
        return {"error": {"code": self.code, "message": self.message, "details": self.details}}


class InvalidParameterError(AuthorWorksError):
    code = "INVALID_PARAMETER"

    def __init__(self, parameter: str, message: str):
        super().__init__(message, {"parameter": parameter})
