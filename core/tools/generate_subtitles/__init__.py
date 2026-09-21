"""生成 ASS 字幕公开入口。只写文件，不烧进视频。"""

from ._constants import (
    SUBTITLE_PRESETS,
    SUPPORTED_SUBTITLE_ANIMATIONS,
    SUPPORTED_SUBTITLE_LANGUAGES,
    SUPPORTED_SUBTITLE_PRESETS,
)
from ._errors import InvalidParameterError, SubtitlesError, UnsupportedSubtitleLanguageError
from .generate_subtitles import generate_subtitles
from ._schema import (
    GENERATE_SUBTITLES_INPUT_SCHEMA,
    GENERATE_SUBTITLES_OUTPUT_SCHEMA,
    SUBTITLE_POSITION_SCHEMA,
    SUBTITLE_STYLE_SCHEMA,
    SUBTITLE_WORD_SCHEMA,
)

__all__ = [
    "generate_subtitles",
    "SubtitlesError",
    "InvalidParameterError",
    "UnsupportedSubtitleLanguageError",
    "SUPPORTED_SUBTITLE_LANGUAGES",
    "SUPPORTED_SUBTITLE_PRESETS",
    "SUPPORTED_SUBTITLE_ANIMATIONS",
    "SUBTITLE_PRESETS",
    "GENERATE_SUBTITLES_INPUT_SCHEMA",
    "GENERATE_SUBTITLES_OUTPUT_SCHEMA",
    "SUBTITLE_POSITION_SCHEMA",
    "SUBTITLE_STYLE_SCHEMA",
    "SUBTITLE_WORD_SCHEMA",
]
