"""片身一次合成：烧字幕、叠贴图、叠配音与可选 BGM / 片头音效 / 封面帧。"""

from __future__ import annotations

import os
import shutil
from pathlib import Path
from uuid import uuid4

from core.tools.generate_bgm import BGM_FADE_IN_SECONDS, BGM_FADE_OUT_SECONDS, BGM_GAIN

from ._constants import (
    VIDEO_AUDIO_CHANNELS,
    VIDEO_AUDIO_CODEC,
    VIDEO_AUDIO_RATE,
    VIDEO_FFMPEG_TIMEOUT_SECONDS,
    VIDEO_FPS,
)
from ._errors import FFmpegNotFoundError, InvalidParameterError, RenderError
from ._ffmpeg import _encode_video_args, _filter_path, _probe, _run, _validate_file
from ._output_name import _output_path
from ._overlay import normalize_overlays, overlay_filtergraph, overlay_input_args

__all__ = ["mix_body"]


def mix_body(
    video_path: str | Path,
    output_path: str | Path,
    *,
    tts_path: str | Path,
    bgm_path: str | Path | None = None,
    ass_path: str | Path | None = None,
    fontsdir: str | Path | None = None,
    overlays: list[dict] | None = None,
    cover_path: str | Path | None = None,
    cover_duration: float | None = None,
    opening_sfx: list[dict] | None = None,
    bgm_start_seconds: float | None = None,
) -> dict:
    """画面烧字幕/贴纸/封面（如有）并重编码；叠 TTS 与可选 BGM、片头音效。原片无音轨。"""
    video = _validate_file(video_path, "video_path")
    tts = _validate_file(tts_path, "tts_path")
    bgm = _validate_file(bgm_path, "bgm_path") if bgm_path else None
    cover = _validate_file(cover_path, "cover_path") if cover_path else None
    ass = None
    if ass_path is not None:
        ass = _validate_file(ass_path, "ass_path")
        if ass.suffix.lower() != ".ass":
            raise InvalidParameterError("ass_path", "字幕必须是 .ass 文件")
    layers = normalize_overlays(overlays)
    sfx_items = []
    for index, item in enumerate(opening_sfx or []):
        if not isinstance(item, dict):
            raise InvalidParameterError(f"opening_sfx[{index}]", "每项必须是对象")
        sfx_items.append({
            "path": _validate_file(item.get("path"), f"opening_sfx[{index}].path"),
            "start": max(0.0, float(item.get("start") or 0)),
            "duration": max(0.05, float(item.get("duration") or 0.05)),
            "gain": float(item.get("gain") or 1.0),
        })
    destination = _output_path(output_path)
    ffmpeg = shutil.which("ffmpeg")
    if not ffmpeg:
        raise FFmpegNotFoundError("ffmpeg")
    probe = _probe(video)
    duration = probe["duration"]
    timeout_seconds = max(VIDEO_FFMPEG_TIMEOUT_SECONDS, duration * 15)
    video_stream = next(
        (item for item in probe.get("streams") or [] if item.get("codec_type") == "video"),
        {},
    )
    width = int(video_stream.get("width") or 0)
    height = int(video_stream.get("height") or 0)
    if width <= 0 or height <= 0:
        raise RenderError("无法读取成片画面尺寸")

    command = [ffmpeg, "-y", "-i", str(video), "-i", str(tts)]
    next_index = 2
    bgm_index = None
    if bgm is not None:
        bgm_index = next_index
        command.extend(["-stream_loop", "-1", "-i", str(bgm)])
        next_index += 1
    sfx_indices = []
    for item in sfx_items:
        sfx_indices.append(next_index)
        command.extend(["-i", str(item["path"])])
        next_index += 1
    cover_index = None
    cover_frames = 0
    if cover is not None:
        try:
            cover_seconds = float(cover_duration or 0)
        except (TypeError, ValueError) as extra:
            raise InvalidParameterError("cover_duration", "有封面时 cover_duration 必须是正数") from extra
        if cover_seconds <= 0:
            raise InvalidParameterError("cover_duration", "有封面时 cover_duration 必须大于 0")
        cover_frames = max(1, round(cover_seconds * VIDEO_FPS))
        cover_index = next_index
        command.extend(["-loop", "1", "-framerate", str(VIDEO_FPS), "-i", str(cover)])
        next_index += 1
    command.extend(overlay_input_args(layers))
    overlay_start = next_index

    video_chains: list[str] = []
    current = "0:v"
    encode_video = bool(ass or layers or cover is not None)
    if ass is not None:
        subtitle_filter = f"subtitles='{_filter_path(ass)}'"
        if fontsdir is not None:
            font_directory = Path(fontsdir).resolve()
            if not font_directory.is_dir():
                raise InvalidParameterError("fontsdir", f"字体目录不存在：{font_directory}")
            subtitle_filter += f":fontsdir='{_filter_path(font_directory)}'"
        video_chains.append(f"[0:v]{subtitle_filter}[subtitled]")
        current = "subtitled"
    if layers:
        video_chains.append(overlay_filtergraph(current, layers, overlay_start))
        current = "vout"
    if cover_index is not None:
        video_chains.append(
            f"[{cover_index}:v]scale={width}:{height}:force_original_aspect_ratio=increase:flags=lanczos,"
            f"crop={width}:{height},setsar=1[cover]"
        )
        video_chains.append(
            f"[{current}][cover]overlay=0:0:enable='lt(n,{cover_frames})'[video]"
        )
        video_map = "[video]"
    elif current == "0:v":
        video_map = "0:v:0"
    else:
        video_map = f"[{current}]"

    audio_chains = [
        f"[1:a]aresample={VIDEO_AUDIO_RATE},aformat=channel_layouts=stereo,"
        f"atrim=0:{duration:.9f},asetpts=PTS-STARTPTS[tts]",
    ]
    mix_labels = ["[tts]"]
    if bgm_index is not None:
        fade_out_start = max(0.0, duration - BGM_FADE_OUT_SECONDS)
        try:
            bgm_start = max(0.0, float(bgm_start_seconds or 0))
        except (TypeError, ValueError) as extra:
            raise InvalidParameterError("bgm_start_seconds", "必须是数字") from extra
        if bgm_start >= duration:
            raise InvalidParameterError(
                "bgm_start_seconds",
                f"BGM 起播时间 {bgm_start:.3f}s 不能大于等于成片时长 {duration:.3f}s",
            )
        audio_chains.append(
            f"[{bgm_index}:a]atrim=0:{duration:.9f},asetpts=PTS-STARTPTS,"
            f"aresample={VIDEO_AUDIO_RATE},aformat=channel_layouts=stereo,"
            f"volume={BGM_GAIN:.6f},"
            f"afade=t=in:st={bgm_start:.3f}:d={BGM_FADE_IN_SECONDS:.3f},"
            f"afade=t=out:st={fade_out_start:.3f}:d={BGM_FADE_OUT_SECONDS:.3f}[bgm]"
        )
        mix_labels.append("[bgm]")
    for index, item in enumerate(sfx_items):
        delay_ms = round(item["start"] * 1000)
        label = f"sfx{index}"
        audio_chains.append(
            f"[{sfx_indices[index]}:a]atrim=0:{item['duration']:.6f},asetpts=PTS-STARTPTS,"
            f"aresample={VIDEO_AUDIO_RATE},aformat=channel_layouts=stereo,"
            f"volume={item['gain']:.3f},adelay={delay_ms}:all=1[{label}]"
        )
        mix_labels.append(f"[{label}]")
    if len(mix_labels) == 1:
        audio_map = "[tts]"
    else:
        audio_chains.append(
            "".join(mix_labels)
            + f"amix=inputs={len(mix_labels)}:duration=first:normalize=0[a]"
        )
        audio_map = "[a]"

    filter_parts = [*video_chains, *audio_chains]
    command.extend(["-filter_complex", ";".join(filter_parts), "-map", video_map, "-map", audio_map])
    command.extend(["-t", f"{duration:.9f}"])
    if encode_video:
        command.extend(_encode_video_args(still_image=False))
    else:
        command.extend(["-c:v", "copy"])
    command.extend([
        "-c:a", VIDEO_AUDIO_CODEC, "-ar", str(VIDEO_AUDIO_RATE), "-ac", str(VIDEO_AUDIO_CHANNELS),
        "-movflags", "+faststart",
    ])
    temporary = destination.with_name(f".{destination.stem}-{uuid4().hex}.tmp.mp4")
    command.append(str(temporary))
    try:
        _run(command, "片身合成", timeout_seconds=timeout_seconds)
        _probe(temporary)
        os.replace(temporary, destination)
    finally:
        if temporary.exists():
            temporary.unlink(missing_ok=True)
    result = _probe(destination)
    return {"output_path": str(destination), "duration": round(result["duration"], 6)}
