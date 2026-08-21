"""静图缩放与运镜滤镜。"""

from __future__ import annotations

from ._constants import SHOT_FPS, SHOT_MOTION_INPUT_SCALE, SHOT_MOTION_WORK_SCALE
from ._errors import InvalidParameterError


def _static_filter(width: int, height: int) -> str:
    return (
        f"scale={width}:{height}:force_original_aspect_ratio=increase:flags=lanczos,"
        f"crop={width}:{height},setsar=1"
    )


def _motion_filter(
    motion: dict,
    duration: float,
    width: int,
    height: int,
    *,
    start_delay: float = 0.0,
) -> str:
    values = {
        "zoom_from": float(motion.get("zoom_from", 1.0)),
        "zoom_to": float(motion.get("zoom_to", motion.get("zoom_from", 1.0))),
        "pan_from_x": float(motion.get("pan_from_x", 0.5)),
        "pan_from_y": float(motion.get("pan_from_y", 0.5)),
        "pan_to_x": float(motion.get("pan_to_x", motion.get("pan_from_x", 0.5))),
        "pan_to_y": float(motion.get("pan_to_y", motion.get("pan_from_y", 0.5))),
    }
    if not 1.0 <= values["zoom_from"] <= 2.0 or not 1.0 <= values["zoom_to"] <= 2.0:
        raise InvalidParameterError("motion", "zoom_from 和 zoom_to 必须在 1.0～2.0 之间")
    for key in ("pan_from_x", "pan_from_y", "pan_to_x", "pan_to_y"):
        if not 0.0 <= values[key] <= 1.0:
            raise InvalidParameterError("motion", f"{key} 必须在 0.0～1.0 之间")
    frames = max(1, round(duration * SHOT_FPS))
    try:
        delay_seconds = float(start_delay)
    except (TypeError, ValueError) as extra:
        raise InvalidParameterError("start_delay", "start_delay 必须是非负数字") from extra
    if delay_seconds < 0:
        raise InvalidParameterError("start_delay", "start_delay 不能小于 0")
    delay_frames = min(frames - 1, round(delay_seconds * SHOT_FPS))
    motion_frames = max(1, frames - delay_frames - 1)
    progress = (
        "1" if frames == 1 else
        (
            f"if(lt(on\\,{delay_frames})\\,0\\,min(1\\,(on-{delay_frames})/{motion_frames}))"
            if delay_frames else f"min(1\\,on/{frames - 1})"
        )
    )
    smooth = f"({progress})*({progress})*(3-2*({progress}))"
    zoom = f"{values['zoom_from']}+({values['zoom_to']}-{values['zoom_from']})*({smooth})"
    pan_x = f"{values['pan_from_x']}+({values['pan_to_x']}-{values['pan_from_x']})*({smooth})"
    pan_y = f"{values['pan_from_y']}+({values['pan_to_y']}-{values['pan_from_y']})*({smooth})"
    camera_input_width = width * SHOT_MOTION_INPUT_SCALE
    camera_input_height = height * SHOT_MOTION_INPUT_SCALE
    work_width = width * SHOT_MOTION_WORK_SCALE
    work_height = height * SHOT_MOTION_WORK_SCALE
    return ",".join([
        f"scale={camera_input_width}:{camera_input_height}:force_original_aspect_ratio=increase:flags=bicubic,setsar=1",
        f"zoompan=z='{zoom}':x='(iw-iw/zoom)*({pan_x})':y='(ih-ih/zoom)*({pan_y})':"
        f"d=1:s={work_width}x{work_height}:fps={SHOT_FPS}",
        f"scale={width}:{height}:flags=lanczos,setsar=1",
    ])


def _frozen_motion_filter(motion: dict, width: int, height: int) -> str:
    """运镜起始构图的定格，只算一帧，供片头遮罩使用。"""
    values = {
        "zoom_from": float(motion.get("zoom_from", 1.0)),
        "pan_from_x": float(motion.get("pan_from_x", 0.5)),
        "pan_from_y": float(motion.get("pan_from_y", 0.5)),
    }
    if not 1.0 <= values["zoom_from"] <= 2.0:
        raise InvalidParameterError("motion", "zoom_from 必须在 1.0～2.0 之间")
    for key in ("pan_from_x", "pan_from_y"):
        if not 0.0 <= values[key] <= 1.0:
            raise InvalidParameterError("motion", f"{key} 必须在 0.0～1.0 之间")
    camera_input_width = width * SHOT_MOTION_INPUT_SCALE
    camera_input_height = height * SHOT_MOTION_INPUT_SCALE
    work_width = width * SHOT_MOTION_WORK_SCALE
    work_height = height * SHOT_MOTION_WORK_SCALE
    zoom = values["zoom_from"]
    pan_x = values["pan_from_x"]
    pan_y = values["pan_from_y"]
    return ",".join([
        "select='eq(n\\,0)'",
        f"scale={camera_input_width}:{camera_input_height}:force_original_aspect_ratio=increase:flags=bicubic,setsar=1",
        f"zoompan=z='{zoom}':x='(iw-iw/zoom)*({pan_x})':y='(ih-ih/zoom)*({pan_y})':"
        f"d=1:s={work_width}x{work_height}:fps={SHOT_FPS}",
        f"scale={width}:{height}:flags=lanczos,setsar=1",
    ])
