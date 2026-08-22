"""Cloudflare 数据服务错误定义。"""

from __future__ import annotations


class CloudflareDataError(Exception):
    """Cloudflare 数据服务错误基类。"""

    code = "CLOUDFLARE_DATA_ERROR"

    def __init__(self, message: str, details: dict | None = None):
        super().__init__(message)
        self.message = message
        self.details = details or {}

    def to_dict(self) -> dict:
        return {"error": {"code": self.code, "message": self.message, "details": self.details}}


class CloudflareDataConfigurationError(CloudflareDataError):
    code = "CLOUDFLARE_DATA_CONFIGURATION_ERROR"


class CloudflareDataRequestError(CloudflareDataError):
    code = "CLOUDFLARE_DATA_REQUEST_ERROR"


class CloudflareDataConflictError(CloudflareDataError):
    code = "CLOUDFLARE_DATA_CONFLICT"

    def __init__(self, message: str, details: dict | None = None, *, remote_code: str = "CONFLICT"):
        super().__init__(message, details)
        self.remote_code = remote_code

