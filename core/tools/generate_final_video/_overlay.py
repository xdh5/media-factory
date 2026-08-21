"""把透明贴图素材叠到视频上。"""

from __future__ import annotations

from pathlib import Path

from ._errors import InvalidParameterError
from ._ffmpeg import _validate_file

_IMAGE_SUFFIXES = {".png", ".webp", ".jpg", ".jpeg"}


def normalize_overlays(overlays: list[dict] | None) -> list[dict]:
    if overlays is None:
        return []
    if not isinstance(overlays, list):
        raise InvalidParameterError("overlays", "overlays 必须是对象列表")
    resolved: list[dict] = []
    for index, item in enumerate(overlays):
        if not isinstance(item, dict):
            raise InvalidParameterError(f"overlays[{index}]", "每项必须是对象")
        raw_path = item.get("path") or item.get("output_path")
        if not raw_path:
            raise InvalidParameterError(
                f"overlays[{index}].path",
                "必须提供 path 或 output_path，指向 generate_sticker 产出的素材",
            )
        path = _validate_file(raw_path, f"overlays[{index}].path")
        try:
            x = int(item.get("x", 0))
            y = int(item.get("y", 0))
        except (TypeError, ValueError) as extra:
            raise InvalidParameterError(f"overlays[{index}].x/y", "叠加坐标必须是整数") from extra
        resolved.append({
            "path": path,
            "x": x,
            "y": y,
            "loop": bool(item.get("loop", True)),
        })
    return resolved


def overlay_input_args(overlays: list[dict]) -> list[str]:
    args: list[str] = []
    for item in overlays:
        path: Path = item["path"]
        if item["loop"]:
            if path.suffix.lower() in _IMAGE_SUFFIXES:
                args.extend(["-loop", "1", "-i", str(path)])
            else:
                args.extend(["-stream_loop", "-1", "-i", str(path)])
        else:
            args.extend(["-i", str(path)])
    return args


def overlay_filtergraph(base_label: str, overlays: list[dict], first_input_index: int) -> str:
    if not overlays:
        raise InvalidParameterError("overlays", "没有可叠加的贴图素材")
    chains: list[str] = []
    current = base_label
    last = len(overlays) - 1
    for index, item in enumerate(overlays):
        source = first_input_index + index
        next_label = "vout" if index == last else f"ov{index}"
        chains.append(
            f"[{current}][{source}:v]overlay=x={item['x']}:y={item['y']}:"
            f"format=auto:eof_action=pass[{next_label}]"
        )
        current = next_label
    return ";".join(chains)
