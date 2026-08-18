"""开场动画错误定义。

错误带 code / message / details，to_dict() 输出 JSON 友好结构，
上层（agent 工具/API）捕获后可直接序列化返回：
    {"error": {"code": "INVALID_PARAMETER", "message": "...", "details": {...}}}
"""

from __future__ import annotations

__all__ = [
    "VideoRenderError",
    "InvalidParameterError",
    "FFMPEGNotFoundError",
    "RenderError",
    "RenderTimeoutError",
]


class VideoRenderError(Exception):
    """开场动画错误基类。子类通过 code 声明错误码。"""

    code = "VIDEO_RENDER_ERROR"

    def __init__(self, message: str, details: dict | None = None):
        super().__init__(message)
        self.message = message
        self.details = details or {}

    def to_dict(self) -> dict:
        return {"error": {"code": self.code, "message": self.message, "details": self.details}}


class InvalidParameterError(VideoRenderError):
    """参数非法（如图片路径不存在）。details.parameter 指出问题参数。"""

    code = "INVALID_PARAMETER"

    def __init__(self, parameter: str, message: str):
        self.parameter = parameter
        super().__init__(message, {"parameter": parameter})


class FFMPEGNotFoundError(VideoRenderError):
    """本机未安装 ffmpeg 或不在 PATH 中。"""

    code = "FFMPEG_NOT_FOUND"


class RenderError(VideoRenderError):
    """ffmpeg 渲染失败。message 携带 stderr 摘要。"""

    code = "RENDER_FAILED"


class RenderTimeoutError(VideoRenderError):
    """开场动画 FFmpeg 执行超时。"""

    code = "RENDER_TIMEOUT"

    def __init__(self, timeout_seconds: float):
        super().__init__(
            f"开场动画超过 {timeout_seconds:.1f} 秒仍未完成，已终止 FFmpeg 子进程",
            {"timeout_seconds": timeout_seconds},
        )
