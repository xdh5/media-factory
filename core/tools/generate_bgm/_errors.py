"""生成 BGM 错误定义。"""

from __future__ import annotations


class BGMError(Exception):
    code = "BGM_ERROR"

    def __init__(self, message: str, details: dict | None = None):
        super().__init__(message)
        self.message = message
        self.details = details or {}

    def to_dict(self) -> dict:
        return {"error": {"code": self.code, "message": self.message, "details": self.details}}


class InvalidParameterError(BGMError):
    code = "INVALID_PARAMETER"

    def __init__(self, parameter: str, message: str):
        super().__init__(message, {"parameter": parameter})


class BGMFileNotFoundError(BGMError):
    code = "BGM_FILE_NOT_FOUND"

    def __init__(self, parameter: str, path: str):
        super().__init__(
            f"{parameter} 指向的文件不存在：{path}",
            {"parameter": parameter, "path": path},
        )


class FFmpegNotFoundError(BGMError):
    code = "FFMPEG_NOT_FOUND"

    def __init__(self, executable: str):
        super().__init__(f"未找到 {executable}，请确认已安装 ffmpeg")


class MediaProbeError(BGMError):
    code = "MEDIA_PROBE_FAILED"


class RenderError(BGMError):
    code = "RENDER_FAILED"


class RenderTimeoutError(BGMError):
    code = "RENDER_TIMEOUT"

    def __init__(self, timeout_seconds: float):
        super().__init__(
            f"生成 BGM 超过 {timeout_seconds:.1f} 秒仍未完成，已终止 FFmpeg",
            {"timeout_seconds": timeout_seconds},
        )
