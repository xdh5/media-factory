"""视频片段拼接、封面一帧前插与最终 BGM 混音。"""

from __future__ import annotations

import os
import shutil
import subprocess
import tempfile
from pathlib import Path

from core.capabilities.bgm._constants import BGM_FADE_IN_SECONDS, BGM_FADE_OUT_SECONDS, BGM_FIXED_GAIN

from ._constants import (
    VIDEO_AUDIO_CHANNELS,
    VIDEO_AUDIO_CODEC,
    VIDEO_AUDIO_RATE,
    VIDEO_CODEC,
    VIDEO_CRF,
    VIDEO_FPS,
    VIDEO_PIXEL_FORMAT,
    VIDEO_PRESET,
)
from ._errors import FFmpegNotFoundError, InvalidParameterError, RenderError
from .render_shot import _probe, _validate_file
from .select_subtitle import _parse_size

__all__ = ["concat_segments", "prepend_cover_frame", "mix_bgm"]


def _ffmpeg() -> str:
    executable = shutil.which("ffmpeg")
    if not executable:
        raise FFmpegNotFoundError("ffmpeg")
    return executable


def _run(command: list[str], context: str) -> None:
    completed = subprocess.run(
        command,
        check=False,
        capture_output=True,
        text=True,
        encoding="utf-8",
        errors="replace",
    )
    if completed.returncode != 0:
        detail = (completed.stderr or completed.stdout or "").strip()[-3000:]
        raise RenderError(f"{context}：{detail or '未知 FFmpeg 错误'}")


def _output_path(value: str | Path) -> Path:
    output = Path(value).resolve()
    if output.suffix.lower() != ".mp4":
        raise InvalidParameterError("output_path", "视频输出必须使用 .mp4 扩展名")
    output.parent.mkdir(parents=True, exist_ok=True)
    return output


def _replace_from_temporary(temporary_output: Path, output: Path) -> None:
    _probe(temporary_output)
    os.replace(temporary_output, output)


def _manifest_line(path: Path) -> str:
    escaped = str(path.resolve()).replace("'", "'\\''")
    return f"file '{escaped}'"


def concat_segments(segment_paths: list[str | Path], output_path: str | Path) -> dict:
    """按顺序无重编码拼接规格一致的视频片段。"""
    if not isinstance(segment_paths, list) or not segment_paths:
        raise InvalidParameterError("segment_paths", "至少传入一个视频片段")
    segments = [_validate_file(path, f"segment_paths[{index}]") for index, path in enumerate(segment_paths)]
    output = _output_path(output_path)
    with tempfile.TemporaryDirectory(prefix="video-concat-", dir=output.parent) as temporary:
        temporary_dir = Path(temporary)
        manifest = temporary_dir / "segments.txt"
        manifest.write_text(
            "\n".join(_manifest_line(path) for path in segments),
            encoding="utf-8",
        )
        temporary_output = temporary_dir / "output.mp4"
        _run(
            [
                _ffmpeg(), "-y", "-f", "concat", "-safe", "0", "-i", str(manifest),
                "-c", "copy", "-movflags", "+faststart", str(temporary_output),
            ],
            "视频片段拼接失败",
        )
        _replace_from_temporary(temporary_output, output)
    return {"output_path": str(output), "duration": round(_probe(output)["duration"], 6), "segment_count": len(segments)}


def prepend_cover_frame(
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
                _ffmpeg(), "-y",
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
        )
        _replace_from_temporary(temporary_output, output)
    return {
        "output_path": str(output),
        "duration": round(_probe(output)["duration"], 6),
        "cover_frames": 1,
        "fps": VIDEO_FPS,
    }


def mix_bgm(
    video_path: str | Path,
    bgm_path: str | Path,
    output_path: str | Path,
    *,
    gain: float = BGM_FIXED_GAIN,
    fade_in: float = BGM_FADE_IN_SECONDS,
    fade_out: float = BGM_FADE_OUT_SECONDS,
) -> dict:
    """在保留旁白和音效的基础上，最后循环并混入 BGM。"""
    video = _validate_file(video_path, "video_path")
    bgm = _validate_file(bgm_path, "bgm_path")
    output = _output_path(output_path)
    duration = _probe(video)["duration"]
    try:
        gain_value = float(gain)
        fade_in_value = max(0.0, min(float(fade_in), duration))
        fade_out_value = max(0.0, min(float(fade_out), duration))
    except (TypeError, ValueError) as exc:
        raise InvalidParameterError("gain/fade", "BGM 音量和淡入淡出必须是数字") from exc
    if gain_value < 0:
        raise InvalidParameterError("gain", "BGM 音量不能小于 0")
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
        + "[music];[main][music]amix=inputs=2:duration=first:normalize=0[a]"
    )
    with tempfile.TemporaryDirectory(prefix="video-bgm-", dir=output.parent) as temporary:
        temporary_output = Path(temporary) / "output.mp4"
        _run(
            [
                _ffmpeg(), "-y", "-i", str(video), "-stream_loop", "-1", "-i", str(bgm),
                "-filter_complex", filter_complex,
                "-map", "0:v:0", "-map", "[a]", "-t", f"{duration:.9f}",
                "-c:v", "copy",
                "-c:a", VIDEO_AUDIO_CODEC, "-ar", str(VIDEO_AUDIO_RATE), "-ac", str(VIDEO_AUDIO_CHANNELS),
                "-movflags", "+faststart", str(temporary_output),
            ],
            "最终 BGM 混音失败",
        )
        _replace_from_temporary(temporary_output, output)
    return {
        "output_path": str(output),
        "duration": round(_probe(output)["duration"], 6),
        "bgm_path": str(bgm),
        "gain": gain_value,
        "fade_in": fade_in_value,
        "fade_out": fade_out_value,
    }
