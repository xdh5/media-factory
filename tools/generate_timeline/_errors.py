"""时间轴章节条工具的错误类型。"""

from __future__ import annotations


class TimelineError(Exception):
    """章节时间轴生成失败。"""

    def __init__(self, message: str, details: dict | None = None) -> None:
        super().__init__(message)
        self.message = message
        self.details = details or {}


class InvalidParameterError(TimelineError):
    """参数不合法。"""
