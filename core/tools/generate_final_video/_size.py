"""视频画布尺寸解析。"""

from __future__ import annotations

import re

from ._errors import InvalidParameterError


def parse_size(size: str) -> tuple[int, int]:
    matched = re.fullmatch(r"\s*(\d+)\s*[xX×]\s*(\d+)\s*", str(size or ""))
    if not matched:
        raise InvalidParameterError("size", "size 必须使用 WIDTHxHEIGHT 格式，例如 1920x1080")
    width, height = (int(value) for value in matched.groups())
    if width < 2 or height < 2 or width % 2 or height % 2:
        raise InvalidParameterError("size", "宽高必须是大于等于 2 的偶数，以兼容 H.264 yuv420p 输出")
    return width, height
