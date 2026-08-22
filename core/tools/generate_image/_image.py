"""生图工具共用的尺寸校验与 PNG 存图实现。"""

from __future__ import annotations

import re
from pathlib import Path
from uuid import uuid4

from PIL import Image, ImageOps

from ._constants import IMAGE_ASPECT_MAX_PIXEL_ERROR
from ._errors import InvalidParameterError


def _parse_size(size: str) -> tuple[int, int, str]:
    matched = re.fullmatch(r"\s*(\d+)\s*[xX×]\s*(\d+)\s*", str(size or ""))
    if not matched:
        raise InvalidParameterError("size", "size 必须使用 WIDTHxHEIGHT 格式，例如 1920x1080")
    width, height = (int(value) for value in matched.groups())
    if width < 64 or height < 64:
        raise InvalidParameterError("size", "size 的宽高都必须不小于 64 像素")
    return width, height, f"{width}x{height}"


def _parse_radio(radio: str) -> tuple[int, int, str]:
    matched = re.fullmatch(r"\s*(\d+)\s*:\s*(\d+)\s*", str(radio or ""))
    if not matched:
        raise InvalidParameterError("radio", "radio 必须使用 WIDTH:HEIGHT 格式，例如 16:9")
    width, height = (int(value) for value in matched.groups())
    if width <= 0 or height <= 0:
        raise InvalidParameterError("radio", "radio 的两个数字都必须大于 0")
    return width, height, f"{width}:{height}"


def _validate_dimensions(radio: str, size: str) -> tuple[int, int, str, str]:
    width, height, normalized_size = _parse_size(size)
    ratio_width, ratio_height, normalized_radio = _parse_radio(radio)
    if width * ratio_height != height * ratio_width:
        raise InvalidParameterError(
            "radio",
            f"radio={normalized_radio} 与 size={normalized_size} 的宽高比不一致，请修改其中一个",
        )
    return width, height, normalized_radio, normalized_size


def _matches_target_aspect(src_width: int, src_height: int, dst_width: int, dst_height: int) -> bool:
    if src_width <= 0 or src_height <= 0 or dst_width <= 0 or dst_height <= 0:
        return False
    expected = round(src_width * dst_height / dst_width)
    return abs(src_height - expected) <= IMAGE_ASPECT_MAX_PIXEL_ERROR


def _fit_image(image: Image.Image, width: int, height: int) -> Image.Image:
    """按目标尺寸缩放；保持图片原始色彩模式和透明通道。"""
    if image.size == (width, height):
        return image
    if _matches_target_aspect(image.width, image.height, width, height):
        return image.resize((width, height), Image.Resampling.LANCZOS)
    return ImageOps.fit(image, (width, height), method=Image.Resampling.LANCZOS)


def _write_png(image: Image.Image, output_path: Path) -> None:
    output_path.parent.mkdir(parents=True, exist_ok=True)
    temporary = output_path.with_name(f".{output_path.stem}-{uuid4().hex}.tmp.png")
    image.save(temporary, format="PNG")
    temporary.replace(output_path)
