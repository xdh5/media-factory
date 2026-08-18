"""开场动画：双向滑入 + 快门闪光，输入一张图片，输出一个 mp4。

迁移自 ai-video-maker 的 _slide_in_shutter_filter。动画时序：
黑白全画幅自左滑入、带柔和投影的 1/2 彩色照片卡自右滑入（smoothstep 缓动），
停顿后在快门时刻叠加白色闪光完成"拍照"，并混入滑入/快门音效。
"""

from __future__ import annotations

import shutil
import subprocess
import tempfile
from pathlib import Path

from core.capabilities.intro._constants import (
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
    SFX_WHOOSH_GAIN,
    SFX_WHOOSH_PATH,
    SFX_WHOOSH_SECONDS,
    SHUTTER_START_SECONDS,
    SLIDE_IN_SECONDS,
    TOTAL_SECONDS,
)
from core.capabilities.intro._errors import (
    FFMPEGNotFoundError,
    InvalidParameterError,
    RenderError,
    RenderTimeoutError,
)
from core.tools.video._constants import (
    SUBTITLE_FONT_DIRECTORIES,
    VIDEO_AUDIO_CHANNELS,
    VIDEO_AUDIO_CODEC,
    VIDEO_AUDIO_RATE,
    VIDEO_CODEC,
    VIDEO_CRF,
    VIDEO_PIXEL_FORMAT,
    VIDEO_PRESET,
)
from core.tools.video._render_shot import (
    _filter_path,
    _motion_filter,
    _probe,
    _static_filter,
    _write_ass,
)

__all__ = ["slide_in_shutter"]


def _build_filter(source: str, duration: float) -> str:
    """生成原版双向滑入、快门和展开遮罩所需的 FFmpeg 片段。"""
    flash_end = min(duration, SHUTTER_START_SECONDS + FLASH_SECONDS)

    # 各阶段起止钳制在片段时长内，保证短片段不越界
    first_end = min(FIRST_SLIDE_SECONDS, max(0.05, duration))
    second_start = min(SECOND_SLIDE_START_SECONDS, max(0.0, duration - 0.05))
    second_end = min(SLIDE_IN_SECONDS, max(second_start + 0.05, duration))

    # smoothstep 缓动：两端速度为零，避免生硬起步/急停
    first_p = f"min(1\\,max(0\\,t/{first_end:.3f}))"
    first_smooth = f"({first_p})*({first_p})*(3-2*({first_p}))"
    second_p = f"min(1\\,max(0\\,(t-{second_start:.3f})/{max(0.05, second_end - second_start):.3f}))"
    second_smooth = f"({second_p})*({second_p})*(3-2*({second_p}))"

    # 照片卡柔和投影：黑底 pad 后抽通道做半透明阴影
    shadow_x = CARD_SHADOW_MARGIN + CARD_SHADOW_OFFSET_X
    shadow_y = CARD_SHADOW_MARGIN + CARD_SHADOW_OFFSET_Y

    return (
        f"[{source}]split=2[slide_full_source][slide_small_source];"
        f"color=c=black:size={CANVAS_SIZE}:r={FPS}:d={duration:.3f},format=rgba[base];"
        f"[slide_full_source]scale={OUTPUT_SIZE}:force_original_aspect_ratio=increase:flags=lanczos,"
        f"crop={OUTPUT_SIZE},setsar=1,format=rgba[full_source];"
        f"[full_source]hue=s=0[first];"
        # 输入是静态图；卡片阴影只需生成一次，后续由 overlay 重复，避免对相同像素逐帧高斯模糊。
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
        # 黑白全画幅自左滑入
        f"[base][first]overlay=x='-W+W*{first_smooth}':y=0:eof_action=repeat[first_stage];"
        # 彩色照片卡自右滑入至画面中央
        f"[first_stage][card]overlay=x='W+((W-w)/2-W)*{second_smooth}':"
        "y='(H-h)/2':eof_action=repeat[intro_card];"
        # 快门时刻叠加白色闪光（淡出）
        f"color=c=white:size={CANVAS_SIZE}:r={FPS}:d={FLASH_SECONDS:.3f},format=rgba,"
        f"fade=t=out:st=0:d={FLASH_SECONDS:.3f}:alpha=1,"
        f"setpts=PTS+{SHUTTER_START_SECONDS:.3f}/TB[flash];"
        f"[intro_card][flash]overlay=0:0:eof_action=pass:"
        f"enable='between(t,{SHUTTER_START_SECONDS:.3f},{flash_end:.3f})'[photo_card]"
    )


def _run(command: list[str], timeout_seconds: float) -> None:
    """执行外部命令，非零退出码时抛出带 stderr 摘要的错误。"""
    try:
        completed = subprocess.run(
            command,
            check=False,
            capture_output=True,
            text=True,
            encoding="utf-8",
            errors="replace",
            timeout=timeout_seconds,
        )
    except subprocess.TimeoutExpired as exc:
        raise RenderTimeoutError(timeout_seconds) from exc
    if completed.returncode != 0:
        details = completed.stderr.strip() or completed.stdout.strip()
        raise RenderError(details[-2000:] or "FFmpeg 渲染失败")


def slide_in_shutter(
    image_path: str | Path,
    tts_path: str | Path,
    output_path: str | Path,
    *,
    audio_start: float = 0,
    audio_end: float | None = None,
    subtitle: str | None = None,
    subtitle_language: str = "zh",
    motion: dict | None = None,
) -> dict:
    """渲染首镜头：旁白从 0 秒开始，先播放开场动画，再继续原镜头动效。"""
    image_path = Path(image_path)
    if not image_path.is_file():
        raise InvalidParameterError(
            "image_path",
            f"输入图片不存在：{image_path}，请确认路径是否正确",
        )
    tts_path = Path(tts_path)
    if not tts_path.is_file():
        raise InvalidParameterError("tts_path", f"TTS 文件不存在：{tts_path}")
    tts_duration = _probe(tts_path)["duration"]
    try:
        effective_start = float(audio_start)
        effective_end = float(audio_end) if audio_end is not None else tts_duration
    except (TypeError, ValueError) as exc:
        raise InvalidParameterError("audio_start/audio_end", "音频起止时间必须是数字") from exc
    if effective_start < 0 or effective_end <= effective_start:
        raise InvalidParameterError("audio_start/audio_end", "必须满足 0 ≤ audio_start < audio_end")
    if effective_end > tts_duration + 0.01:
        raise InvalidParameterError(
            "audio_end",
            f"audio_end={effective_end:.6f} 超过 TTS 真实时长 {tts_duration:.6f}",
        )
    effective_end = min(effective_end, tts_duration)
    duration = effective_end - effective_start
    output_path = Path(output_path)
    output_path.parent.mkdir(parents=True, exist_ok=True)

    ffmpeg = shutil.which("ffmpeg")
    if not ffmpeg:
        raise FFMPEGNotFoundError(
            "未找到 ffmpeg，请先安装并加入 PATH（如 winget install Gyan.FFmpeg）",
        )

    with tempfile.TemporaryDirectory(prefix="slide-in-shutter-") as temporary:
        temporary_dir = Path(temporary)
        intro_duration = min(TOTAL_SECONDS, duration)
        flash_end = min(intro_duration, SHUTTER_START_SECONDS + FLASH_SECONDS)
        expand_end = min(intro_duration, flash_end + PHOTO_EXPAND_SECONDS)
        # 正常首镜头从一张图直接展开为帧序列；片头支路只补齐自身时长，
        # 保留原版画面但不反复解码同一张 PNG。
        command = [ffmpeg, "-y", "-framerate", str(FPS), "-i", str(image_path)]
        command.extend([
            "-ss", f"{effective_start:.6f}", "-t", f"{duration:.6f}", "-i", str(tts_path),
        ])
        chains: list[str] = []
        if intro_duration > 0.0001:
            chains.append("[0:v]split=2[normal_input][intro_raw]")
            chains.append(
                f"[intro_raw]tpad=stop_mode=clone:stop_duration={intro_duration:.6f}[intro_input]"
            )
            if motion:
                normal_filter = _motion_filter(
                    motion,
                    duration,
                    OUTPUT_WIDTH,
                    OUTPUT_HEIGHT,
                    single_image=True,
                    start_delay=expand_end,
                )
            else:
                normal_filter = (
                    f"tpad=stop_mode=clone:stop_duration={duration:.6f},"
                    f"{_static_filter(OUTPUT_WIDTH, OUTPUT_HEIGHT)}"
                )
            chains.append(
                f"[normal_input]{normal_filter},trim=duration={duration:.6f},"
                "setpts=PTS-STARTPTS,format=rgba[normal_source]"
            )
            chains.append(_build_filter("intro_input", intro_duration))
            # 展开底图和展开遮罩都取自首镜头动效的起始画面。这样四向展开完成后
            # 交给正常动效时，前后两帧的缩放与焦点完全一致，不再从 1.00 倍
            # 突然跳到 zoom_from 造成二次放大和停顿感。
            chains.extend([
                "[normal_source]split=3[normal][expand_colour_source][expand_gray_raw]",
                "[expand_gray_raw]hue=s=0[expand_gray_source]",
            ])
            expand_duration = max(0.05, expand_end - flash_end)
            expand_p = f"min(1\\,max(0\\,(t-{flash_end:.3f})/{expand_duration:.3f}))"
            expand_smooth = f"({expand_p})*({expand_p})*(3-2*({expand_p}))"
            half_width = OUTPUT_WIDTH // 2
            half_height = OUTPUT_HEIGHT // 2
            chains.extend([
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
                f"enable='lte(t,{expand_end:.3f})'[base_video]",
            ])
        else:
            chains.append(f"[0:v]{_static_filter(OUTPUT_WIDTH, OUTPUT_HEIGHT)}[base_video]")

        video_label = "base_video"
        if subtitle is not None and str(subtitle).strip():
            subtitle_file = temporary_dir / "subtitle.ass"
            _write_ass(subtitle_file, str(subtitle), duration, subtitle_language, RESOLUTION)
            subtitle_filter = f"subtitles='{_filter_path(subtitle_file)}'"
            font_directory = next(
                (Path(value) for value in SUBTITLE_FONT_DIRECTORIES if Path(value).is_dir()),
                None,
            )
            if font_directory:
                subtitle_filter += f":fontsdir='{_filter_path(font_directory)}'"
            chains.append(f"[base_video]{subtitle_filter}[subtitled_video]")
            video_label = "subtitled_video"
        chains.append(f"[{video_label}]format={VIDEO_PIXEL_FORMAT}[video]")

        chains.append(
            f"[1:a]atrim=0:{duration:.6f},asetpts=PTS-STARTPTS,"
            f"aresample={VIDEO_AUDIO_RATE},aformat=channel_layouts=stereo[tts]"
        )
        mix_labels = ["[tts]"]
        sfx: list[str] = []
        next_input = 2
        if SFX_WHOOSH_PATH.is_file():
            command.extend(["-i", str(SFX_WHOOSH_PATH)])
            chains.append(
                f"[{next_input}:a]atrim=0:{min(SFX_WHOOSH_SECONDS, duration):.6f},"
                f"asetpts=PTS-STARTPTS,aresample={VIDEO_AUDIO_RATE},"
                f"aformat=channel_layouts=stereo,volume={SFX_WHOOSH_GAIN:.3f}[whoosh]"
            )
            mix_labels.append("[whoosh]")
            sfx.append("whoosh")
            next_input += 1
        if SFX_SHUTTER_PATH.is_file() and duration > SHUTTER_START_SECONDS:
            command.extend(["-i", str(SFX_SHUTTER_PATH)])
            delay_ms = round(SHUTTER_START_SECONDS * 1000)
            chains.append(
                f"[{next_input}:a]atrim=0:{min(SFX_SHUTTER_SECONDS, duration - SHUTTER_START_SECONDS):.6f},"
                f"asetpts=PTS-STARTPTS,aresample={VIDEO_AUDIO_RATE},aformat=channel_layouts=stereo,"
                f"volume={SFX_SHUTTER_GAIN:.3f},adelay={delay_ms}:all=1[shutter]"
            )
            mix_labels.append("[shutter]")
            sfx.append("shutter")
        chains.append(
            "".join(mix_labels)
            + f"amix=inputs={len(mix_labels)}:duration=first:normalize=0[audio]"
        )

        command.extend([
            "-filter_complex", ";".join(chains),
            "-map", "[video]", "-map", "[audio]",
            "-t", f"{duration:.6f}", "-r", str(FPS),
            "-c:v", VIDEO_CODEC, "-preset", VIDEO_PRESET, "-crf", str(VIDEO_CRF),
            "-pix_fmt", VIDEO_PIXEL_FORMAT,
            "-c:a", VIDEO_AUDIO_CODEC, "-ar", str(VIDEO_AUDIO_RATE), "-ac", str(VIDEO_AUDIO_CHANNELS),
            "-movflags", "+faststart", str(output_path),
        ])
        render_timeout = max(
            INTRO_RENDER_MIN_TIMEOUT_SECONDS,
            duration * INTRO_RENDER_TIMEOUT_PER_SECOND,
        )
        _run(command, render_timeout)

    return {
        "output_path": str(output_path),
        "duration": round(duration, 6),
        "fps": FPS,
        "resolution": RESOLUTION,
        "sfx": sfx,
        "audio_start": round(effective_start, 6),
        "audio_end": round(effective_end, 6),
        "has_subtitle": bool(subtitle is not None and str(subtitle).strip()),
        "has_motion": bool(motion),
    }
