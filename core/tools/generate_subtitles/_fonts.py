"""字幕字体目录解析。"""

from __future__ import annotations

from pathlib import Path

from ._constants import SUBTITLE_DEFAULT_FONT_PATH
from ._errors import MediaFileNotFoundError


def resolve_fontsdir() -> Path:
    """返回包内字幕字体目录；缺失时直接报错，不依赖系统字体。"""
    if not SUBTITLE_DEFAULT_FONT_PATH.is_file():
        raise MediaFileNotFoundError(
            "font",
            f"{SUBTITLE_DEFAULT_FONT_PATH}；请确认 static/font 已包含 PUTUI-Regular.ttf",
        )
    return SUBTITLE_DEFAULT_FONT_PATH.parent
