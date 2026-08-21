"""成片工具错误。失败时抛出 FinalVideoError 子类。"""

from __future__ import annotations


class FinalVideoError(Exception):
    """成片错误基类。"""

    code = "FINAL_VIDEO_ERROR"

    def __init__(self, message: str, details: dict | None = None):
        super().__init__(message)
        self.message = message
        self.details = details or {}

    def to_dict(self) -> dict:
        return {"error": {"code": self.code, "message": self.message, "details": self.details}}


class InvalidParameterError(FinalVideoError):
    """输入参数无效。"""

    code = "INVALID_PARAMETER"

    def __init__(self, parameter: str, message: str):
        super().__init__(message, {"parameter": parameter})


class MediaFileNotFoundError(FinalVideoError):
    """图片或音频文件不存在。"""

    code = "MEDIA_FILE_NOT_FOUND"

    def __init__(self, parameter: str, path: str):
        super().__init__(
            f"{parameter} 指向的文件不存在：{path}",
            {"parameter": parameter, "path": path},
        )


class FFmpegNotFoundError(FinalVideoError):
    """FFmpeg 或 FFprobe 不可用。"""

    code = "FFMPEG_NOT_FOUND"

    def __init__(self, executable: str):
        super().__init__(f"未找到 {executable}，请确认 Docker 镜像已安装 ffmpeg")


class MediaProbeError(FinalVideoError):
    """无法读取媒体时长或流信息。"""

    code = "MEDIA_PROBE_FAILED"


class RenderError(FinalVideoError):
    """FFmpeg 渲染失败。"""

    code = "RENDER_FAILED"


class RenderTimeoutError(FinalVideoError):
    """FFmpeg 执行超过允许时间。"""

    code = "RENDER_TIMEOUT"

    def __init__(self, context: str, timeout_seconds: float):
        super().__init__(
            f"{context}超过 {timeout_seconds:.1f} 秒仍未完成，已终止 FFmpeg 子进程",
            {"context": context, "timeout_seconds": timeout_seconds},
        )


class CacheError(FinalVideoError):
    """镜头缓存读写或校验失败。"""

    code = "CACHE_FAILED"
