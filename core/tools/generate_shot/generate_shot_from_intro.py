"""按片头样式生成第一镜。"""

from __future__ import annotations

from pathlib import Path

from ._constants import INTRO_STYLES
from ._errors import InvalidParameterError
from ._page_flip import page_flip
from ._slide_in_shutter import slide_in_shutter

__all__ = ["generate_shot_from_intro", "intro_bgm_start_seconds"]


def intro_bgm_start_seconds(style: str, *, first_shot_duration: float) -> float:
    """片头拍照/翻页动画结束后再叠 BGM 的起播时间（秒）。"""
    from ._constants import FLASH_SECONDS, PHOTO_EXPAND_SECONDS, SHUTTER_START_SECONDS

    kind = str(style or "").strip()
    duration = float(first_shot_duration)
    if duration <= 0:
        return 0.0
    if kind == "slide_in_shutter":
        flash_end = SHUTTER_START_SECONDS + FLASH_SECONDS
        return min(duration, flash_end + PHOTO_EXPAND_SECONDS)
    return 0.0


def generate_shot_from_intro(
    style: str,
    output_path: str | Path,
    *,
    duration: float,
    image_path: str | Path | None = None,
    image_paths: list[str | Path] | None = None,
    sfx_path: str | Path | None = None,
    motion: dict | None = None,
) -> dict:
    """渲染片头镜头：只出画面，不烧配音、字幕、贴纸或 BGM。"""
    kind = str(style or "").strip()
    if kind not in INTRO_STYLES:
        raise InvalidParameterError(
            "style",
            f"未知片头样式：{style!r}。当前支持 {', '.join(INTRO_STYLES)}",
        )
    if kind == "page_flip":
        if not image_paths:
            raise InvalidParameterError("image_paths", "page_flip 必须传入 image_paths")
        if sfx_path is None:
            raise InvalidParameterError("sfx_path", "page_flip 必须传入 sfx_path")
        return page_flip(
            image_paths,
            output_path,
            sfx_path,
            duration=duration,
        )
    if image_path is None:
        raise InvalidParameterError("image_path", "slide_in_shutter 必须传入 image_path")
    return slide_in_shutter(
        image_path,
        output_path,
        duration=duration,
        motion=motion,
    )
