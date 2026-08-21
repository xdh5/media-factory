"""清理缓存错误定义。"""


class ClearCacheError(Exception):
    code = "CLEAR_CACHE_ERROR"

    def __init__(self, message: str, details: dict | None = None):
        super().__init__(message)
        self.message = message
        self.details = details or {}

    def to_dict(self) -> dict:
        return {"error": {"code": self.code, "message": self.message, "details": self.details}}


class InvalidParameterError(ClearCacheError):
    code = "INVALID_PARAMETER"

    def __init__(self, parameter: str, message: str):
        super().__init__(message, {"parameter": parameter})


class ConfirmationRequiredError(ClearCacheError):
    code = "CONFIRMATION_REQUIRED"


class RunDirectoryError(ClearCacheError):
    code = "RUN_DIRECTORY_ERROR"
