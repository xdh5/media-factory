"""按顺序 copy 拼接已编码的 MP4，不重编码画面。"""

from __future__ import annotations

import os
import shutil
import subprocess
import tempfile
from pathlib import Path

from ._constants import VIDEO_FFMPEG_TIMEOUT_SECONDS
from ._errors import CacheError, FFmpegNotFoundError, InvalidParameterError, RenderError, RenderTimeoutError
from ._output_name import _output_path
from .render_shot import _probe, _validate_file

__all__ = ["concat_videos"]


def _concat_manifest_line(path: Path) -> str:
    escaped = str(path.resolve()).replace("'", "'\\''")
    return f"file '{escaped}'"


def concat_videos(segment_paths: list[str | Path], output_path: str | Path) -> dict:
    """按顺序 copy 拼接已编码的 MP4，不重编码画面。"""
    if not isinstance(segment_paths, list) or not segment_paths:
        raise InvalidParameterError("segment_paths", "segment_paths 必须是至少一个视频路径")
    paths = [_validate_file(path, f"segment_paths[{index}]") for index, path in enumerate(segment_paths)]
    output = _output_path(output_path)
    ffmpeg = shutil.which("ffmpeg")
    if not ffmpeg:
        raise FFmpegNotFoundError("ffmpeg")
    with tempfile.TemporaryDirectory(prefix="video-concat-", dir=output.parent) as temporary:
        temporary_dir = Path(temporary)
        manifest = temporary_dir / "segments.txt"
        manifest.write_text("\n".join(_concat_manifest_line(path) for path in paths), encoding="utf-8")
        temporary_output = temporary_dir / "output.mp4"
        try:
            completed = subprocess.run(
                [
                    ffmpeg, "-y", "-f", "concat", "-safe", "0", "-i", str(manifest),
                    "-c", "copy", "-movflags", "+faststart", str(temporary_output),
                ],
                check=False,
                capture_output=True,
                text=True,
                encoding="utf-8",
                errors="replace",
                timeout=VIDEO_FFMPEG_TIMEOUT_SECONDS,
            )
        except subprocess.TimeoutExpired as extra:
            raise RenderTimeoutError("视频拼接", VIDEO_FFMPEG_TIMEOUT_SECONDS) from extra
        if completed.returncode != 0:
            detail = (completed.stderr or completed.stdout or "").strip()[-3000:]
            raise RenderError(f"视频拼接失败：{detail}")
        try:
            _probe(temporary_output)
            os.replace(temporary_output, output)
        except OSError as extra:
            raise CacheError(f"无法原子替换视频：{output}") from extra
    probe = _probe(output)
    return {"output_path": str(output), "duration": round(probe["duration"], 6)}
