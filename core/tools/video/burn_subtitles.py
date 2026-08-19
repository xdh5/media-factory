"""整片只烧一次字幕，避免每个镜头重复跑 libass。"""

from __future__ import annotations

import tempfile
from pathlib import Path

from ._constants import SUBTITLE_FONT_DIRECTORIES, VIDEO_FFMPEG_TIMEOUT_SECONDS
from ._errors import InvalidParameterError
from ._output_name import _output_path, _replace_from_temporary
from .render_shot import _encode_video_args, _executable, _filter_path, _probe, _run, _validate_file, _write_timeline_ass

__all__ = ["burn_subtitles"]


def burn_subtitles(
    video_path: str | Path,
    cues: list[dict],
    size: str,
    output_path: str | Path,
) -> dict:
    """按时间轴把字幕烧进已合成的视频。cues 每项含 start、end、text，可选 language。"""
    if not isinstance(cues, list) or not cues:
        raise InvalidParameterError("cues", "cues 必须是至少一条字幕")
    video = _validate_file(video_path, "video_path")
    output = _output_path(output_path)
    with tempfile.TemporaryDirectory(prefix="video-subtitles-", dir=output.parent) as temporary:
        temporary_dir = Path(temporary)
        subtitle_file = temporary_dir / "timeline.ass"
        _write_timeline_ass(subtitle_file, cues, size)
        subtitle_filter = f"subtitles='{_filter_path(subtitle_file)}'"
        font_directory = next(
            (Path(value) for value in SUBTITLE_FONT_DIRECTORIES if Path(value).is_dir()),
            None,
        )
        if font_directory:
            subtitle_filter += f":fontsdir='{_filter_path(font_directory)}'"
        temporary_output = temporary_dir / "output.mp4"
        _run(
            [
                _executable("ffmpeg"), "-y", "-i", str(video),
                "-vf", subtitle_filter,
                *_encode_video_args(still_image=False),
                "-c:a", "copy",
                "-movflags", "+faststart",
                str(temporary_output),
            ],
            "整片字幕烧录失败",
            timeout_seconds=VIDEO_FFMPEG_TIMEOUT_SECONDS,
        )
        _replace_from_temporary(temporary_output, output)
    return {"output_path": str(output), "duration": round(_probe(output)["duration"], 6)}
