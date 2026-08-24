"""仅通过千问生图，不包含宿主失败次数或业务兜底策略。"""

from __future__ import annotations

import json
from pathlib import Path
from uuid import uuid4

from PIL import Image

from ._errors import InvalidParameterError
from ._image import _parse_size
from ._qwen import _generate_with_ai, _qwen_image_model, _save_image

__all__ = ["generate_qwen_image"]


def _load_cached_image(
    destination: Path,
    *,
    width: int,
    height: int,
    cache_signature: str | None,
) -> dict | None:
    """签名和尺寸都一致时复用现有图片，避免失败重试覆盖已完成镜头。"""
    if not cache_signature or not destination.is_file():
        return None
    metadata_path = destination.with_suffix(".json")
    if not metadata_path.is_file():
        return None
    try:
        metadata = json.loads(metadata_path.read_text(encoding="utf-8"))
        if metadata.get("cache_signature") != cache_signature:
            return None
        with Image.open(destination) as image:
            image.load()
            if image.size != (width, height):
                return None
            has_alpha = "A" in image.getbands()
            alpha_extrema = image.getchannel("A").getextrema() if has_alpha else (255, 255)
            return {
                "mode": image.mode,
                "has_alpha": has_alpha,
                "alpha_extrema": [int(alpha_extrema[0]), int(alpha_extrema[1])],
                "has_transparency": bool(has_alpha and alpha_extrema[0] < 255),
            }
    except (OSError, ValueError, json.JSONDecodeError):
        return None


def generate_qwen_image(
    prompt: str,
    output_path: str | Path,
    *,
    size: str,
    reference_image_paths: list[str | Path] | None = None,
    cache_signature: str | None = None,
) -> dict:
    """优先复用签名一致的现有图片，否则调用千问生图并写入目标路径。"""
    text = str(prompt or "").strip()
    if not text:
        raise InvalidParameterError("prompt", "prompt 不能为空")
    width, height, normalized_size = _parse_size(size)
    destination = Path(output_path).resolve()
    references = [Path(str(path)).resolve() for path in (reference_image_paths or [])]
    cached = _load_cached_image(
        destination,
        width=width,
        height=height,
        cache_signature=cache_signature,
    )
    if cached is not None:
        return {
            "output_path": str(destination),
            "size": normalized_size,
            "provider": "dashscope",
            "model": _qwen_image_model(),
            "cache_hit": True,
            **cached,
        }
    image_bytes = _generate_with_ai(text, references, normalized_size)
    image_info = _save_image(image_bytes, destination, width, height)
    if cache_signature:
        metadata_path = destination.with_suffix(".json")
        temporary = metadata_path.with_name(f".{metadata_path.stem}-{uuid4().hex}.tmp.json")
        temporary.write_text(
            json.dumps({"cache_signature": cache_signature}, ensure_ascii=False, sort_keys=True),
            encoding="utf-8",
        )
        temporary.replace(metadata_path)
    return {
        "output_path": str(destination),
        "size": normalized_size,
        "provider": "dashscope",
        "model": _qwen_image_model(),
        "cache_hit": False,
        **image_info,
    }
