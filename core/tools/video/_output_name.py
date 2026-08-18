"""视频成品标题文件名与落盘。"""

from __future__ import annotations

import os
import shutil
import tempfile
from pathlib import Path

from ._constants import (
    MAX_OUTPUT_FILENAME_STEM_LENGTH,
    WINDOWS_FORBIDDEN_FILENAME_CHARACTERS,
    WINDOWS_RESERVED_FILENAMES,
)
from ._errors import InvalidParameterError
from ._render_shot import _probe


def _titled_output_path(output_dir: str | Path, title: str, suffix: str = ".mp4") -> Path:
    """按标题生成跨 Windows 可用的成品输出路径。"""
    if not isinstance(title, str) or not title.strip():
        raise InvalidParameterError("title", "title 必须是非空字符串，成品文件名将使用该标题")
    if not isinstance(suffix, str) or not suffix.startswith(".") or len(suffix) < 2:
        raise InvalidParameterError("suffix", "suffix 必须是以 . 开头的扩展名，例如 .mp4")

    normalized = "".join("_" if character in WINDOWS_FORBIDDEN_FILENAME_CHARACTERS else character for character in title)
    normalized = normalized.strip().rstrip(". ")
    if not normalized:
        raise InvalidParameterError("title", "title 去除 Windows 不支持的字符后为空，无法生成文件名")
    if normalized.upper() in WINDOWS_RESERVED_FILENAMES:
        normalized = f"_{normalized}"
    normalized = normalized[:MAX_OUTPUT_FILENAME_STEM_LENGTH].rstrip(". ")
    if not normalized:
        raise InvalidParameterError("title", "title 截断后为空，无法生成文件名")
    return Path(output_dir).resolve() / f"{normalized}{suffix}"


def _output_path(value: str | Path) -> Path:
    output = Path(value).resolve()
    if output.suffix.lower() != ".mp4":
        raise InvalidParameterError("output_path", "视频输出必须使用 .mp4 扩展名")
    output.parent.mkdir(parents=True, exist_ok=True)
    return output


def _replace_from_temporary(temporary_output: Path, output: Path) -> None:
    _probe(temporary_output)
    os.replace(temporary_output, output)


def _write_titled_video(source: str | Path, output_dir: str | Path, title: str) -> Path:
    """把成片按标题写入输出目录。"""
    source_path = Path(source).resolve()
    output = _output_path(_titled_output_path(output_dir, title))
    if source_path == output:
        _probe(output)
        return output
    with tempfile.TemporaryDirectory(prefix="video-output-", dir=output.parent) as temporary:
        temporary_output = Path(temporary) / "output.mp4"
        shutil.copy2(source_path, temporary_output)
        _replace_from_temporary(temporary_output, output)
    return output
