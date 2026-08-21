"""生成贴图素材错误定义。"""

from __future__ import annotations


class StickerError(Exception):
    """生成贴图错误基类。"""

    code = "STICKER_ERROR"

    def __init__(self, message: str, details: dict | None = None):
        super().__init__(message)
        self.message = message
        self.details = details or {}

    def to_dict(self) -> dict:
        return {"error": {"code": self.code, "message": self.message, "details": self.details}}


class InvalidParameterError(StickerError):
    code = "INVALID_PARAMETER"

    def __init__(self, parameter: str, message: str):
        super().__init__(message, {"parameter": parameter})


class StickerFontError(StickerError):
    code = "STICKER_FONT_MISSING"

    def __init__(self, path: str):
        super().__init__(
            f"贴图字体不存在：{path}；请确认 static/font 已包含 ArialMdm.ttf",
            {"path": path},
        )


class FFmpegNotFoundError(StickerError):
    code = "FFMPEG_NOT_FOUND"

    def __init__(self, executable: str):
        super().__init__(f"未找到 {executable}，请确认 Docker 镜像已安装 ffmpeg")


class RenderError(StickerError):
    code = "RENDER_FAILED"


class RenderTimeoutError(StickerError):
    code = "RENDER_TIMEOUT"

    def __init__(self, context: str, timeout_seconds: float):
        super().__init__(
            f"{context}超过 {timeout_seconds:.1f} 秒仍未完成，已终止 FFmpeg 子进程",
            {"context": context, "timeout_seconds": timeout_seconds},
        )
