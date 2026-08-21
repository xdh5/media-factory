"""按标识生成贴图素材。只写文件，不烧进视频。"""

from __future__ import annotations

from pathlib import Path

from ._constants import STICKER_REC, SUPPORTED_STICKERS
from ._errors import InvalidParameterError
from ._rec import write_rec_sticker

__all__ = ["generate_sticker"]


def _canvas_size(width: int, height: int) -> tuple[int, int]:
    try:
        canvas_width = int(width)
        canvas_height = int(height)
    except (TypeError, ValueError) as extra:
        raise InvalidParameterError("width/height", "画布宽高必须是整数") from extra
    if canvas_width < 2 or canvas_height < 2 or canvas_width % 2 or canvas_height % 2:
        raise InvalidParameterError(
            "width/height",
            f"画布宽高必须是大于等于 2 的偶数，当前为 {canvas_width}x{canvas_height}",
        )
    return canvas_width, canvas_height


def _normalize_sticker(sticker: str) -> str:
    name = str(sticker or "").strip()
    if not name:
        raise InvalidParameterError(
            "sticker",
            f"必须指定贴图标识，可用值：{list(SUPPORTED_STICKERS)}",
        )
    if name not in SUPPORTED_STICKERS:
        raise InvalidParameterError(
            "sticker",
            f"未知贴图 {name!r}，可用值：{list(SUPPORTED_STICKERS)}。REC 只是其中一项，请改传已支持的标识",
        )
    return name


def generate_sticker(
    sticker: str,
    output_path: str | Path,
    width: int,
    height: int,
) -> dict:
    """生成一张可贴到成片上的素材。sticker 必填；rec 为可选标识之一。"""
    name = _normalize_sticker(sticker)
    _canvas_size(width, height)
    destination = Path(output_path).resolve()
    if name == STICKER_REC:
        if destination.suffix.lower() != ".mov":
            raise InvalidParameterError("output_path", "rec 贴图必须使用 .mov 扩展名（透明循环素材）")
        extra = write_rec_sticker(destination, int(height))
        return {
            "output_path": str(destination),
            "sticker": name,
            **extra,
        }
    raise InvalidParameterError(
        "sticker",
        f"尚未实现贴图 {name!r} 的素材生成，可用值：{list(SUPPORTED_STICKERS)}",
    )
