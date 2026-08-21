"""视频输出路径与原子落盘。"""

from __future__ import annotations

import os
from pathlib import Path

from ._errors import InvalidParameterError
from ._ffmpeg import _probe

INVALID_FILENAME_CHARS = '<>:"/\\|?*'


def safe_filename(title: str) -> str:
    """把标题转成可用文件名，仅替换系统非法字符。"""
    name = "".join("_" if char in INVALID_FILENAME_CHARS else char for char in str(title or "").strip())
    name = name.rstrip(" .")
    if not name:
        raise InvalidParameterError("title", "标题为空，无法生成文件名")
    return name


def _output_path(value: str | Path) -> Path:
    output = Path(value).resolve()
    if output.suffix.lower() != ".mp4":
        raise InvalidParameterError("output_path", "视频输出必须使用 .mp4 扩展名")
    output.parent.mkdir(parents=True, exist_ok=True)
    return output


def _replace_from_temporary(temporary_output: Path, output: Path) -> None:
    _probe(temporary_output)
    os.replace(temporary_output, output)
