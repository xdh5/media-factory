"""视频合成工具错误定义。"""

from __future__ import annotations


class VideoToolError(Exception):
    """视频工具错误基类。"""

    code = "VIDEO_TOOL_ERROR"

    def __init__(self, message: str, details: dict | None = None):
        super().__init__(message)
        self.message = message
        self.details = details or {}

    def to_dict(self) -> dict:
        return {"error": {"code": self.code, "message": self.message, "details": self.details}}


class InvalidParameterError(VideoToolError):
    """输入参数无效。"""

    code = "INVALID_PARAMETER"

    def __init__(self, parameter: str, message: str):
        super().__init__(message, {"parameter": parameter})


class UnsupportedSubtitleLanguageError(VideoToolError):
    """字幕语言不受支持。"""

    code = "UNSUPPORTED_SUBTITLE_LANGUAGE"

    def __init__(self, language: str, supported: list[str]):
        super().__init__(
            f"不支持字幕语言 {language!r}，可用值：{supported}",
            {"language": language, "supported_languages": supported},
        )


class MediaFileNotFoundError(VideoToolError):
    """图片或音频文件不存在。"""

    code = "MEDIA_FILE_NOT_FOUND"

    def __init__(self, parameter: str, path: str):
        super().__init__(
            f"{parameter} 指向的文件不存在：{path}",
            {"parameter": parameter, "path": path},
        )


class FFmpegNotFoundError(VideoToolError):
    """FFmpeg 或 FFprobe 不可用。"""

    code = "FFMPEG_NOT_FOUND"

    def __init__(self, executable: str):
        super().__init__(f"未找到 {executable}，请确认 Docker 镜像已安装 ffmpeg")


class MediaProbeError(VideoToolError):
    """无法读取媒体时长或流信息。"""

    code = "MEDIA_PROBE_FAILED"


class RenderError(VideoToolError):
    """FFmpeg 渲染失败。"""

    code = "RENDER_FAILED"


class CacheError(VideoToolError):
    """镜头缓存读写或校验失败。"""

    code = "CACHE_FAILED"

