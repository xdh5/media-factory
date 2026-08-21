"""从图片生成镜头的错误定义。"""

from __future__ import annotations


class ShotToolError(Exception):
    """镜头生成错误基类。"""

    code = "SHOT_TOOL_ERROR"

    def __init__(self, message: str, details: dict | None = None):
        super().__init__(message)
        self.message = message
        self.details = details or {}

    def to_dict(self) -> dict:
        return {"error": {"code": self.code, "message": self.message, "details": self.details}}


class InvalidParameterError(ShotToolError):
    """输入参数无效。"""

    code = "INVALID_PARAMETER"

    def __init__(self, parameter: str, message: str):
        super().__init__(message, {"parameter": parameter})


class MediaFileNotFoundError(ShotToolError):
    """图片文件不存在。"""

    code = "MEDIA_FILE_NOT_FOUND"

    def __init__(self, parameter: str, path: str):
        super().__init__(
            f"{parameter} 指向的文件不存在：{path}",
            {"parameter": parameter, "path": path},
        )


class FFmpegNotFoundError(ShotToolError):
    """FFmpeg 或 FFprobe 不可用。"""

    code = "FFMPEG_NOT_FOUND"

    def __init__(self, executable: str):
        super().__init__(f"未找到 {executable}，请确认 Docker 镜像已安装 ffmpeg")


class MediaProbeError(ShotToolError):
    """无法读取媒体时长或流信息。"""

    code = "MEDIA_PROBE_FAILED"


class RenderError(ShotToolError):
    """FFmpeg 渲染失败。"""

    code = "RENDER_FAILED"


class RenderTimeoutError(ShotToolError):
    """FFmpeg 执行超过允许时间。"""

    code = "RENDER_TIMEOUT"

    def __init__(self, context: str, timeout_seconds: float):
        super().__init__(
            f"{context}超过 {timeout_seconds:.1f} 秒仍未完成，已终止 FFmpeg 子进程",
            {"context": context, "timeout_seconds": timeout_seconds},
        )
