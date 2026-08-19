"""视频输出路径与原子落盘。"""

from __future__ import annotations

import os
from pathlib import Path

from ._errors import InvalidParameterError
from .render_shot import _probe


def _output_path(value: str | Path) -> Path:
    output = Path(value).resolve()
    if output.suffix.lower() != ".mp4":
        raise InvalidParameterError("output_path", "视频输出必须使用 .mp4 扩展名")
    output.parent.mkdir(parents=True, exist_ok=True)
    return output


def _replace_from_temporary(temporary_output: Path, output: Path) -> None:
    _probe(temporary_output)
    os.replace(temporary_output, output)
