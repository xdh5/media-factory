"""仅通过千问生图，不包含宿主失败次数或业务兜底策略。"""

from __future__ import annotations

import json
from pathlib import Path
from uuid import uuid4

from ._errors import InvalidParameterError
from ._image import _parse_size
from ._qwen import _generate_with_ai, _qwen_image_model, _save_image

__all__ = ["generate_qwen_image"]


def generate_qwen_image(
    prompt: str,
    output_path: str | Path,
    *,
    size: str,
    reference_image_paths: list[str | Path] | None = None,
    cache_signature: str | None = None,
) -> dict:
    """调用千问生成一张图并写入 output_path。"""
    text = str(prompt or "").strip()
    if not text:
        raise InvalidParameterError("prompt", "prompt 不能为空")
    width, height, normalized_size = _parse_size(size)
    destination = Path(output_path).resolve()
    references = [Path(str(path)).resolve() for path in (reference_image_paths or [])]
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
        **image_info,
    }
