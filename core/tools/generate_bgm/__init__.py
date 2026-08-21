"""生成 BGM 公开入口：按时长循环或裁剪，产出固定音量的音轨。"""

from ._constants import BGM_CINEMATIC_PIANO_PATH, BGM_FADE_IN_SECONDS, BGM_FADE_OUT_SECONDS, BGM_GAIN
from ._errors import BGMError
from .generate_bgm import generate_bgm

__all__ = [
    "generate_bgm",
    "BGM_CINEMATIC_PIANO_PATH",
    "BGM_GAIN",
    "BGM_FADE_IN_SECONDS",
    "BGM_FADE_OUT_SECONDS",
    "BGMError",
]
