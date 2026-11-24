"""视频下载错误。"""

from __future__ import annotations


class DownloadError(Exception):
    """下载工具错误基类。"""

    code = "DOWNLOAD_ERROR"

    def __init__(self, message: str, details: dict | None = None):
        super().__init__(message)
        self.message = message
        self.details = details or {}

    def to_dict(self) -> dict:
        return {"error": {"code": self.code, "message": self.message, "details": self.details}}


class InvalidParameterError(DownloadError):
    code = "INVALID_PARAMETER"

    def __init__(self, parameter: str, message: str):
        super().__init__(message, {"parameter": parameter})


class ParseLinkError(DownloadError):
    code = "PARSE_LINK_FAILED"


class FFmpegNotFoundError(DownloadError):
    code = "FFMPEG_NOT_FOUND"

    def __init__(self) -> None:
        super().__init__("未找到 ffmpeg，请确认已安装并加入 PATH")
