"""生成 ASS 字幕错误定义。"""

from __future__ import annotations


class SubtitlesError(Exception):
    """生成字幕错误基类。"""

    code = "SUBTITLES_ERROR"

    def __init__(self, message: str, details: dict | None = None):
        super().__init__(message)
        self.message = message
        self.details = details or {}

    def to_dict(self) -> dict:
        return {"error": {"code": self.code, "message": self.message, "details": self.details}}


class InvalidParameterError(SubtitlesError):
    code = "INVALID_PARAMETER"

    def __init__(self, parameter: str, message: str):
        super().__init__(message, {"parameter": parameter})


class UnsupportedSubtitleLanguageError(SubtitlesError):
    code = "UNSUPPORTED_SUBTITLE_LANGUAGE"

    def __init__(self, language: str, supported: list[str]):
        super().__init__(
            f"不支持字幕语言 {language!r}，可用值：{supported}",
            {"language": language, "supported_languages": supported},
        )


class MediaFileNotFoundError(SubtitlesError):
    code = "MEDIA_FILE_NOT_FOUND"

    def __init__(self, parameter: str, path: str):
        super().__init__(
            f"{parameter} 指向的文件不存在：{path}",
            {"parameter": parameter, "path": path},
        )
