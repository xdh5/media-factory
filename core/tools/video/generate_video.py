"""最终出片：镜头合成后可选加封面、可选混 BGM，再按标题落盘。"""

from __future__ import annotations

import tempfile
from pathlib import Path

from core.capabilities.bgm._constants import (
    BGM_FADE_IN_SECONDS,
    BGM_FADE_OUT_SECONDS,
    BGM_FIXED_GAIN,
    BGM_MIX_GAIN,
)

from ._compose_video import _compose_video
from ._constants import (
    VIDEO_AUDIO_CHANNELS,
    VIDEO_AUDIO_CODEC,
    VIDEO_AUDIO_RATE,
    VIDEO_CODEC,
    VIDEO_CRF,
    VIDEO_FPS,
    VIDEO_FFMPEG_TIMEOUT_SECONDS,
    VIDEO_PIXEL_FORMAT,
    VIDEO_PRESET,
)
from ._mix_bgm import _mix_bgm
from ._output_name import _output_path, _replace_from_temporary, _titled_output_path, _write_titled_video
from ._render_shot import _executable, _probe, _run, _validate_file
from ._select_subtitle import _parse_size

__all__ = ["generate_video"]


def _prepend_cover_frame(
    cover_path: str | Path,
    video_path: str | Path,
    output_path: str | Path,
    *,
    size: str,
) -> dict:
    """把封面图编码成一帧放在视频最前面，并同步后移原音频。"""
    width, height = _parse_size(size)
    cover = _validate_file(cover_path, "cover_path")
    video = _validate_file(video_path, "video_path")
    output = _output_path(output_path)
    probe = _probe(video)
    duration = probe["duration"]
    has_audio = any(stream.get("codec_type") == "audio" for stream in probe["streams"])
    frame_duration = 1 / VIDEO_FPS
    total_duration = duration + frame_duration
    video_filter = (
        f"[0:v]scale={width}:{height}:force_original_aspect_ratio=increase:flags=lanczos,"
        f"crop={width}:{height},setsar=1,trim=end_frame=1,setpts=PTS-STARTPTS[vcover];"
        "[1:v]setpts=PTS-STARTPTS[vmain];"
        "[vcover][vmain]concat=n=2:v=1:a=0[v]"
    )
    if has_audio:
        audio_filter = (
            f";anullsrc=r={VIDEO_AUDIO_RATE}:cl=stereo:d={frame_duration:.9f}[silence];"
            f"[1:a]aresample={VIDEO_AUDIO_RATE},aformat=channel_layouts=stereo,asetpts=PTS-STARTPTS[main_audio];"
            "[silence][main_audio]concat=n=2:v=0:a=1[a]"
        )
    else:
        audio_filter = f";anullsrc=r={VIDEO_AUDIO_RATE}:cl=stereo:d={total_duration:.9f}[a]"

    with tempfile.TemporaryDirectory(prefix="video-cover-", dir=output.parent) as temporary:
        temporary_output = Path(temporary) / "output.mp4"
        _run(
            [
                _executable("ffmpeg"), "-y",
                "-loop", "1", "-framerate", str(VIDEO_FPS), "-i", str(cover),
                "-i", str(video),
                "-filter_complex", video_filter + audio_filter,
                "-map", "[v]", "-map", "[a]",
                "-t", f"{total_duration:.9f}", "-r", str(VIDEO_FPS),
                "-c:v", VIDEO_CODEC, "-preset", VIDEO_PRESET, "-crf", str(VIDEO_CRF),
                "-pix_fmt", VIDEO_PIXEL_FORMAT,
                "-c:a", VIDEO_AUDIO_CODEC, "-ar", str(VIDEO_AUDIO_RATE), "-ac", str(VIDEO_AUDIO_CHANNELS),
                "-movflags", "+faststart", str(temporary_output),
            ],
            "封面一帧前插失败",
            timeout_seconds=VIDEO_FFMPEG_TIMEOUT_SECONDS,
        )
        _replace_from_temporary(temporary_output, output)
    return {
        "output_path": str(output),
        "duration": round(_probe(output)["duration"], 6),
        "cover_frames": 1,
        "fps": VIDEO_FPS,
    }


def _optional_path(value: str | Path | None, parameter: str) -> Path | None:
    if value is None:
        return None
    text = str(value).strip()
    if not text:
        return None
    return _validate_file(text, parameter)


def generate_video(
    shots: list[dict],
    *,
    size: str,
    cache_dir: str | Path,
    output_dir: str | Path,
    title: str,
    cover_path: str | Path | None = None,
    bgm_path: str | Path | None = None,
    force_shot_ids: list[str] | None = None,
    gain: float = BGM_FIXED_GAIN,
    mix_gain: float = BGM_MIX_GAIN,
    fade_in: float = BGM_FADE_IN_SECONDS,
    fade_out: float = BGM_FADE_OUT_SECONDS,
) -> dict:
    """合成镜头并写出成品；cover_path 和 bgm_path 都不传则只出成片。"""
    cache_root = Path(cache_dir).resolve()
    cache_root.mkdir(parents=True, exist_ok=True)
    composed_path = cache_root / "composed.mp4"
    compose_result = _compose_video(
        shots,
        composed_path,
        cache_root / "shots",
        size=size,
        force_shot_ids=force_shot_ids,
    )
    current = Path(compose_result["output_path"])
    cover = _optional_path(cover_path, "cover_path")
    if cover is not None:
        with_cover_path = cache_root / "with-cover.mp4"
        _prepend_cover_frame(cover, current, with_cover_path, size=size)
        current = with_cover_path

    bgm = _optional_path(bgm_path, "bgm_path")
    bgm_result = None
    if bgm is not None:
        output = _output_path(_titled_output_path(output_dir, title))
        bgm_result = _mix_bgm(
            current,
            bgm,
            output,
            gain=gain,
            mix_gain=mix_gain,
            fade_in=fade_in,
            fade_out=fade_out,
        )
    else:
        output = _write_titled_video(current, output_dir, title)

    probe = _probe(output)
    return {
        "output_path": str(output),
        "duration": round(probe["duration"], 6),
        "shot_count": compose_result["shot_count"],
        "cache_hits": compose_result["cache_hits"],
        "rendered_shots": compose_result["rendered_shots"],
        "shots": compose_result["shots"],
        "has_cover": cover is not None,
        "has_bgm": bgm is not None,
        "bgm_path": None if bgm_result is None else bgm_result["bgm_path"],
        "gain": None if bgm_result is None else bgm_result["gain"],
        "mix_gain": None if bgm_result is None else bgm_result["mix_gain"],
        "fade_in": None if bgm_result is None else bgm_result["fade_in"],
        "fade_out": None if bgm_result is None else bgm_result["fade_out"],
    }
