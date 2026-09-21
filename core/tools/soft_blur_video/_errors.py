"""磨砂滤镜错误定义。"""

from __future__ import annotations


class SoftBlurError(Exception):
    """磨砂滤镜处理失败。"""

    def __init__(self, message: str, details: dict | None = None) -> None:
        super().__init__(message)
        self.message = message
        self.details = details or {}


class SoftBlurTimeoutError(SoftBlurError):
    """FFmpeg 处理超时。"""
