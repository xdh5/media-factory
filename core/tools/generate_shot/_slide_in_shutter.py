"""开场动画：双向滑入 + 快门闪光，然后接同一镜的运镜，一次渲完。"""

from __future__ import annotations

from pathlib import Path

from ._constants import (
    CANVAS_SIZE,
    CARD_SCALE,
    CARD_SHADOW_BLUR,
    CARD_SHADOW_MARGIN,
    CARD_SHADOW_OFFSET_X,
    CARD_SHADOW_OFFSET_Y,
    CARD_SHADOW_OPACITY,
    FIRST_SLIDE_SECONDS,
    FLASH_SECONDS,
    FPS,
    INTRO_RENDER_MIN_TIMEOUT_SECONDS,
    INTRO_RENDER_TIMEOUT_PER_SECOND,
    OUTPUT_SIZE,
    OUTPUT_HEIGHT,
    OUTPUT_WIDTH,
    PHOTO_EXPAND_SECONDS,
    RESOLUTION,
    SECOND_SLIDE_START_SECONDS,
    SFX_SHUTTER_GAIN,
    SFX_SHUTTER_PATH,
    SFX_SHUTTER_SECONDS,
    SFX_ALERT_GAIN,
    SFX_ALERT_PATH,
    SFX_ALERT_SECONDS,
    SHUTTER_START_SECONDS,
    SLIDE_IN_SECONDS,
    TOTAL_SECONDS,
    SHOT_PIXEL_FORMAT,
)
from ._errors import InvalidParameterError
from ._ffmpeg import _encode_video_args, _executable, _run
from ._filters import _motion_filter, _static_filter

__all__ = ["slide_in_shutter"]


def _build_filter(source: str, duration: float) -> str:
    """生成双向滑入、快门闪光所需的 FFmpeg 片段。"""
    flash_end = min(duration, SHUTTER_START_SECONDS + FLASH_SECONDS)
    first_end = min(FIRST_SLIDE_SECONDS, max(0.05, duration))
    second_start = min(SECOND_SLIDE_START_SECONDS, max(0.0, duration - 0.05))
    second_end = min(SLIDE_IN_SECONDS, max(second_start + 0.05, duration))
    first_p = f"min(1\\,max(0\\,t/{first_end:.3f}))"
    first_smooth = f"({first_p})*({first_p})*(3-2*({first_p}))"
    second_p = f"min(1\\,max(0\\,(t-{second_start:.3f})/{max(0.05, second_end - second_start):.3f}))"
    second_smooth = f"({second_p})*({second_p})*(3-2*({second_p}))"
    shadow_x = CARD_SHADOW_MARGIN + CARD_SHADOW_OFFSET_X
    shadow_y = CARD_SHADOW_MARGIN + CARD_SHADOW_OFFSET_Y
    return (
        f"[{source}]split=2[slide_full_source][slide_small_source];"
        f"color=c=black:size={CANVAS_SIZE}:r={FPS}:d={duration:.3f},format=rgba[base];"
        f"[slide_full_source]scale={OUTPUT_SIZE}:force_original_aspect_ratio=increase:flags=lanczos,"
        f"crop={OUTPUT_SIZE},setsar=1,format=rgba[full_source];"
        f"[full_source]hue=s=0[first];"
        f"[slide_small_source]select='eq(n\\,0)',"
        f"scale={round(OUTPUT_WIDTH * CARD_SCALE)}:{round(OUTPUT_HEIGHT * CARD_SCALE)}:"
        "force_original_aspect_ratio=decrease:flags=lanczos,"
        "setsar=1,format=rgba,split=2[photo][shadow_source];"
        f"[shadow_source]pad=iw+{CARD_SHADOW_MARGIN * 2}:ih+{CARD_SHADOW_MARGIN * 2}:"
        f"{shadow_x}:{shadow_y}:color=black@0,"
        f"colorchannelmixer=rr=0:gg=0:bb=0:aa={CARD_SHADOW_OPACITY:.2f},"
        f"gblur=sigma={CARD_SHADOW_BLUR}[shadow];"
        f"[photo]pad=iw+{CARD_SHADOW_MARGIN * 2}:ih+{CARD_SHADOW_MARGIN * 2}:"
        f"{CARD_SHADOW_MARGIN}:{CARD_SHADOW_MARGIN}:color=black@0[photo_padded];"
        "[shadow][photo_padded]overlay=0:0:format=auto[card];"
        f"[base][first]overlay=x='-W+W*{first_smooth}':y=0:eof_action=repeat[first_stage];"
        f"[first_stage][card]overlay=x='W+((W-w)/2-W)*{second_smooth}':"
        "y='(H-h)/2':eof_action=repeat[intro_card];"
        f"color=c=white:size={CANVAS_SIZE}:r={FPS}:d={FLASH_SECONDS:.3f},format=rgba,"
        f"fade=t=out:st=0:d={FLASH_SECONDS:.3f}:alpha=1,"
        f"setpts=PTS+{SHUTTER_START_SECONDS:.3f}/TB[flash];"
        f"[intro_card][flash]overlay=0:0:eof_action=pass:"
        f"enable='between(t,{SHUTTER_START_SECONDS:.3f},{flash_end:.3f})'[photo_card]"
    )


def _expand_chains(flash_end: float, expand_end: float) -> list[str]:
    expand_duration = max(0.05, expand_end - flash_end)
    expand_p = f"min(1\\,max(0\\,(t-{flash_end:.3f})/{expand_duration:.3f}))"
    expand_smooth = f"({expand_p})*({expand_p})*(3-2*({expand_p}))"
    half_width = OUTPUT_WIDTH // 2
    half_height = OUTPUT_HEIGHT // 2
    return [
        "[normal_source]split=3[normal][expand_colour_source][expand_gray_raw]",
        "[expand_gray_raw]hue=s=0[expand_gray_source]",
        "[expand_gray_source]split=4[expand_top_source][expand_bottom_source]"
        "[expand_left_source][expand_right_source]",
        f"[expand_top_source]crop={OUTPUT_WIDTH}:{half_height}:0:0[expand_top]",
        f"[expand_bottom_source]crop={OUTPUT_WIDTH}:{half_height}:0:{half_height}[expand_bottom]",
        f"[expand_left_source]crop={half_width}:{OUTPUT_HEIGHT}:0:0[expand_left]",
        f"[expand_right_source]crop={half_width}:{OUTPUT_HEIGHT}:{half_width}:0[expand_right]",
        f"[expand_colour_source][expand_top]overlay=x=0:y='-{half_height}*{expand_smooth}':"
        "eof_action=repeat[expand_1]",
        f"[expand_1][expand_bottom]overlay=x=0:y='{half_height}+{half_height}*{expand_smooth}':"
        "eof_action=repeat[expand_2]",
        f"[expand_2][expand_left]overlay=x='-{half_width}*{expand_smooth}':y=0:"
        "eof_action=repeat[expand_3]",
        f"[expand_3][expand_right]overlay=x='{half_width}+{half_width}*{expand_smooth}':y=0:"
        "eof_action=repeat[expand_stage]",
        f"[expand_stage][photo_card]overlay=0:0:eof_action=pass:"
        f"enable='lte(t,{flash_end:.3f})'[opening_timeline]",
        f"[normal][opening_timeline]overlay=0:0:eof_action=pass:"
        f"enable='lte(t,{expand_end:.3f})'[opening_video]",
    ]


def slide_in_shutter(
    image_path: str | Path,
    output_path: str | Path,
    *,
    duration: float,
    motion: dict | None = None,
) -> dict:
    """片头动画与剩余运镜一次渲成无音 mp4。音效在成片时叠加。"""
    image_path = Path(image_path)
    if not image_path.is_file():
        raise InvalidParameterError(
            "image_path",
            f"输入图片不存在：{image_path}，请确认路径是否正确",
        )
    try:
        duration = float(duration)
    except (TypeError, ValueError) as extra:
        raise InvalidParameterError("duration", "duration 必须是正数") from extra
    if duration <= 0:
        raise InvalidParameterError("duration", "必须传入大于 0 的 duration")
    output_path = Path(output_path)
    output_path.parent.mkdir(parents=True, exist_ok=True)

    intro_duration = min(TOTAL_SECONDS, duration)
    remaining = max(0.0, duration - intro_duration)
    flash_end = min(duration, SHUTTER_START_SECONDS + FLASH_SECONDS)
    expand_end = min(duration, flash_end + PHOTO_EXPAND_SECONDS)
    camera = (
        _motion_filter(motion, duration, OUTPUT_WIDTH, OUTPUT_HEIGHT, start_delay=expand_end)
        if motion else _static_filter(OUTPUT_WIDTH, OUTPUT_HEIGHT)
    )
    ffmpeg = _executable("ffmpeg")
    chains = [
        "[0:v]split=2[camera_source][intro_raw]",
        f"[intro_raw]tpad=stop_mode=clone:stop_duration={duration:.6f}[intro_input]",
        (
            f"[camera_source]tpad=stop_mode=clone:stop_duration={duration:.6f},"
            f"{camera},trim=duration={duration:.6f},setpts=PTS-STARTPTS,format=rgba[normal_source]"
        ),
        _build_filter("intro_input", duration),
        *_expand_chains(flash_end, expand_end),
        (
            f"[opening_video]trim=duration={duration:.6f},setpts=PTS-STARTPTS,"
            f"format={SHOT_PIXEL_FORMAT}[video]"
        ),
    ]
    command = [
        ffmpeg, "-y", "-hide_banner", "-nostats", "-loglevel", "error",
        "-loop", "1", "-framerate", str(FPS),
        "-t", f"{duration:.6f}", "-i", str(image_path),
        "-filter_complex", ";".join(chains),
        "-map", "[video]", "-an",
        "-t", f"{duration:.6f}", "-r", str(FPS),
        *_encode_video_args(still_image=False),
        str(output_path),
    ]
    _run(
        command,
        "开场动画",
        timeout_seconds=max(
            INTRO_RENDER_MIN_TIMEOUT_SECONDS,
            duration * INTRO_RENDER_TIMEOUT_PER_SECOND,
        ),
    )
    sfx: list[str] = []
    opening_sfx: list[dict] = []
    if SFX_ALERT_PATH.is_file():
        sfx.append("alert")
        opening_sfx.append({
            "path": str(SFX_ALERT_PATH),
            "start": 0.0,
            "duration": SFX_ALERT_SECONDS,
            "gain": SFX_ALERT_GAIN,
        })
    if SFX_SHUTTER_PATH.is_file() and duration > SHUTTER_START_SECONDS:
        sfx.append("shutter")
        opening_sfx.append({
            "path": str(SFX_SHUTTER_PATH),
            "start": SHUTTER_START_SECONDS,
            "duration": SFX_SHUTTER_SECONDS,
            "gain": SFX_SHUTTER_GAIN,
        })
    return {
        "output_path": str(output_path),
        "duration": round(duration, 6),
        "fps": FPS,
        "resolution": RESOLUTION,
        "sfx": sfx,
        "opening_sfx": opening_sfx,
        "has_motion": bool(motion) and remaining >= (1 / FPS),
        "intro_duration": round(intro_duration, 6),
        "tail_duration": round(remaining, 6),
    }
