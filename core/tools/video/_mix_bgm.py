"""把 BGM 循环混入成片。"""

from __future__ import annotations

import tempfile
from pathlib import Path

from core.capabilities.bgm._constants import (
    BGM_FADE_IN_SECONDS,
    BGM_FADE_OUT_SECONDS,
    BGM_FIXED_GAIN,
    BGM_MIX_GAIN,
)

from ._constants import VIDEO_AUDIO_CHANNELS, VIDEO_AUDIO_CODEC, VIDEO_AUDIO_RATE, VIDEO_FFMPEG_TIMEOUT_SECONDS
from ._errors import InvalidParameterError
from ._output_name import _output_path, _replace_from_temporary
from ._render_shot import _executable, _probe, _run, _validate_file


def _mix_bgm(
    video_path: str | Path,
    bgm_path: str | Path,
    output_path: str | Path,
    *,
    gain: float = BGM_FIXED_GAIN,
    mix_gain: float = BGM_MIX_GAIN,
    fade_in: float = BGM_FADE_IN_SECONDS,
    fade_out: float = BGM_FADE_OUT_SECONDS,
) -> dict:
    """在保留旁白和音效的基础上循环并混入 BGM。"""
    video = _validate_file(video_path, "video_path")
    bgm = _validate_file(bgm_path, "bgm_path")
    output = _output_path(output_path)
    duration = _probe(video)["duration"]
    try:
        gain_value = float(gain)
        mix_gain_value = float(mix_gain)
        fade_in_value = max(0.0, min(float(fade_in), duration))
        fade_out_value = max(0.0, min(float(fade_out), duration))
    except (TypeError, ValueError) as exc:
        raise InvalidParameterError("gain/mix_gain/fade", "BGM 音量、整体增益和淡入淡出必须是数字") from exc
    if gain_value < 0 or mix_gain_value < 0:
        raise InvalidParameterError("gain/mix_gain", "BGM 音量和整体增益不能小于 0")
    fade_out_start = max(0.0, duration - fade_out_value)
    music_filters = [
        f"[1:a]atrim=0:{duration:.9f}",
        "asetpts=PTS-STARTPTS",
        f"aresample={VIDEO_AUDIO_RATE}",
        "aformat=channel_layouts=stereo",
        f"volume={gain_value:.6f}",
    ]
    if fade_in_value > 0:
        music_filters.append(f"afade=t=in:st=0:d={fade_in_value:.6f}")
    if fade_out_value > 0:
        music_filters.append(f"afade=t=out:st={fade_out_start:.6f}:d={fade_out_value:.6f}")
    filter_complex = (
        f"[0:a]aresample={VIDEO_AUDIO_RATE},aformat=channel_layouts=stereo[main];"
        + ",".join(music_filters)
        + f"[music];[main][music]amix=inputs=2:duration=first:normalize=0,volume={mix_gain_value:.6f}[a]"
    )
    with tempfile.TemporaryDirectory(prefix="video-bgm-", dir=output.parent) as temporary:
        temporary_output = Path(temporary) / "output.mp4"
        _run(
            [
                _executable("ffmpeg"), "-y", "-i", str(video), "-stream_loop", "-1", "-i", str(bgm),
                "-filter_complex", filter_complex,
                "-map", "0:v:0", "-map", "[a]", "-t", f"{duration:.9f}",
                "-c:v", "copy",
                "-c:a", VIDEO_AUDIO_CODEC, "-ar", str(VIDEO_AUDIO_RATE), "-ac", str(VIDEO_AUDIO_CHANNELS),
                "-movflags", "+faststart", str(temporary_output),
            ],
            "最终 BGM 混音失败",
            timeout_seconds=VIDEO_FFMPEG_TIMEOUT_SECONDS,
        )
        _replace_from_temporary(temporary_output, output)
    return {
        "output_path": str(output),
        "duration": round(_probe(output)["duration"], 6),
        "bgm_path": str(bgm),
        "gain": gain_value,
        "mix_gain": mix_gain_value,
        "fade_in": fade_in_value,
        "fade_out": fade_out_value,
    }
