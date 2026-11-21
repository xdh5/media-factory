"""从图片或片头生成单镜头公开入口。"""

from ._constants import (
    INTRO_RENDERER_VERSION,
    SFX_SHUTTER_GAIN,
    SFX_SHUTTER_PATH,
    SFX_SHUTTER_SECONDS,
    SFX_ALERT_GAIN,
    SFX_ALERT_PATH,
    SFX_ALERT_SECONDS,
    SHOT_RENDERER_VERSION,
    SHUTTER_START_SECONDS,
)
from ._errors import ShotToolError
from .generate_shot_from_image import generate_shot_from_image
from .generate_shot_from_intro import generate_shot_from_intro, intro_bgm_start_seconds

__all__ = [
    "SHOT_RENDERER_VERSION",
    "INTRO_RENDERER_VERSION",
    "SFX_ALERT_PATH",
    "SFX_SHUTTER_PATH",
    "SFX_ALERT_SECONDS",
    "SFX_SHUTTER_SECONDS",
    "SFX_ALERT_GAIN",
    "SFX_SHUTTER_GAIN",
    "SHUTTER_START_SECONDS",
    "ShotToolError",
    "generate_shot_from_image",
    "generate_shot_from_intro",
    "intro_bgm_start_seconds",
]
