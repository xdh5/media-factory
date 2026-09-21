"""生成 ASS 字幕公开入口。只写文件，不烧进视频。"""

from ._constants import SUPPORTED_SUBTITLE_LANGUAGES
from ._errors import InvalidParameterError, SubtitlesError, UnsupportedSubtitleLanguageError
from .generate_subtitles import generate_subtitles
from ._schema import SUBTITLE_POSITION_SCHEMA, SUBTITLE_STYLE_SCHEMA

__all__ = [
    "generate_subtitles",
    "SubtitlesError",
    "InvalidParameterError",
    "UnsupportedSubtitleLanguageError",
    "SUPPORTED_SUBTITLE_LANGUAGES",
    "SUBTITLE_POSITION_SCHEMA",
    "SUBTITLE_STYLE_SCHEMA",
]
