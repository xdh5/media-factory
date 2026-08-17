"""批量配音合成：台词 + 音色 -> 单个 WAV + 每行真实时间轴。

每行先走 synthesize() 生成 Edge MP3，再用 FFmpeg 处理为 24 kHz
单声道 PCM WAV。时间轴由 WAV 采样帧数计算，并与最终拼接音频核对。
"""

from __future__ import annotations

import asyncio
import shutil
import subprocess
import tempfile
import wave
from concurrent.futures import ThreadPoolExecutor, as_completed
from pathlib import Path

from core.tools.tts._constants import (
    TTS_BETWEEN_SENTENCE_TRAILING_SECONDS,
    TTS_CHANNELS,
    TTS_CONCURRENCY,
    TTS_ENDING_PADDING_SECONDS,
    TTS_SAMPLE_RATE,
    TTS_SILENCE_DETECTION_SECONDS,
    TTS_SILENCE_KEEP_COMPENSATION_SECONDS,
    TTS_SILENCE_THRESHOLD_DB,
)
from core.tools.tts._errors import (
    AudioProcessingError,
    EmptyTextError,
    FFmpegNotFoundError,
    InvalidOutputPathError,
)
from core.tools.tts.synthesize import synthesize

__all__ = ["compose"]


def _split_lines(script: str) -> list[str]:
    """按行拆分台词，跳过空行。"""
    return [line.strip() for line in script.splitlines() if line.strip()]


def _wav_frames(path: Path) -> int:
    """读取 PCM WAV 采样帧数，并校验格式是否符合时间轴约定。"""
    try:
        with wave.open(str(path), "rb") as audio:
            if audio.getframerate() != TTS_SAMPLE_RATE or audio.getnchannels() != TTS_CHANNELS:
                raise AudioProcessingError(
                    f"WAV 格式不符合 {TTS_SAMPLE_RATE} Hz、{TTS_CHANNELS} 声道约定：{path}"
                )
            return audio.getnframes()
    except AudioProcessingError:
        raise
    except (OSError, EOFError, wave.Error) as exc:
        raise AudioProcessingError(f"无法读取 WAV 采样时长：{path}") from exc


def _run_ffmpeg(ffmpeg: str, command: list[str], context: str) -> None:
    """执行 FFmpeg，失败时返回可理解的上下文和 stderr 摘要。"""
    result = subprocess.run(
        [ffmpeg, "-y", *command],
        capture_output=True,
        text=True,
        encoding="utf-8",
        errors="replace",
        check=False,
    )
    if result.returncode != 0:
        detail = (result.stderr or "").strip()[-1200:]
        raise AudioProcessingError(f"{context}：{detail or '未知 FFmpeg 错误'}")


def compose(script: str, output_path: str | Path, voice: str) -> dict:
    """把多行台词并发合成为一个 WAV，返回 dict（可直接 json.dumps）：
    {"line_count": 行数, "total_duration": 总时长秒,
     "timeline": [{id, text, start, end, duration}, ...], "output_path": 音频路径}

    timeline 的 start/end 按处理后 PCM WAV 采样帧数累加，
    句间和末尾静音已计入；最终文件采样帧数必须与时间轴完全相等。
    """
    lines = _split_lines(script)
    if not lines:
        raise EmptyTextError("请至少输入一行非空台词")

    output_path = Path(output_path)
    if output_path.suffix.lower() != ".wav":
        raise InvalidOutputPathError(str(output_path))
    output_path.parent.mkdir(parents=True, exist_ok=True)
    ffmpeg = shutil.which("ffmpeg")
    if not ffmpeg:
        raise FFmpegNotFoundError()

    with tempfile.TemporaryDirectory(prefix="tts-compose-") as temporary:
        temporary_dir = Path(temporary)
        segments: list[dict | None] = [None] * len(lines)

        def _synthesize_line(index: int, line: str) -> dict:
            raw_path = temporary_dir / f"line-{index:04d}.mp3"
            segment_path = temporary_dir / f"line-{index:04d}.wav"
            asyncio.run(synthesize(line, raw_path, voice))
            trailing_silence = (
                TTS_ENDING_PADDING_SECONDS
                if index == len(lines)
                else TTS_BETWEEN_SENTENCE_TRAILING_SECONDS
            )
            retained_silence = trailing_silence + TTS_SILENCE_KEEP_COMPENSATION_SECONDS
            edge_trim = (
                "areverse,"
                "silenceremove="
                f"start_periods=1:start_duration={TTS_SILENCE_DETECTION_SECONDS:.3f}:"
                f"start_threshold={TTS_SILENCE_THRESHOLD_DB:.1f}dB:"
                f"start_silence={retained_silence:.3f},"
                "areverse"
            )
            _run_ffmpeg(
                ffmpeg,
                [
                    "-i", str(raw_path),
                    "-af", edge_trim,
                    "-ac", str(TTS_CHANNELS),
                    "-ar", str(TTS_SAMPLE_RATE),
                    "-c:a", "pcm_s16le",
                    str(segment_path),
                ],
                f"第 {index} 行静音处理失败",
            )
            frames = _wav_frames(segment_path)
            if frames <= 0:
                raise AudioProcessingError(f"第 {index} 行处理后没有可用音频")
            return {"audio_path": str(segment_path), "frames": frames}

        first_error: Exception | None = None
        with ThreadPoolExecutor(
            max_workers=min(TTS_CONCURRENCY, len(lines)),
            thread_name_prefix="tts-compose",
        ) as executor:
            futures = {
                executor.submit(_synthesize_line, index, line): index - 1
                for index, line in enumerate(lines, 1)
            }
            for future in as_completed(futures):
                try:
                    segments[futures[future]] = future.result()
                except Exception as exc:
                    first_error = first_error or exc
        if first_error:
            raise first_error

        concat_file = temporary_dir / "segments.txt"
        concat_file.write_text(
            "".join(f"file '{Path(seg['audio_path']).as_posix()}'\n" for seg in segments),
            encoding="utf-8",
        )
        _run_ffmpeg(
            ffmpeg,
            [
                "-f", "concat", "-safe", "0", "-i", str(concat_file),
                "-vn",
                "-ac", str(TTS_CHANNELS),
                "-ar", str(TTS_SAMPLE_RATE),
                "-c:a", "pcm_s16le",
                str(output_path),
            ],
            "拼接完整配音失败",
        )

    timeline: list[dict] = []
    cursor_frames = 0
    for index, (line, seg) in enumerate(zip(lines, segments), 1):
        frames = seg["frames"]
        start = cursor_frames / TTS_SAMPLE_RATE
        cursor_frames += frames
        end = cursor_frames / TTS_SAMPLE_RATE
        timeline.append({
            "id": f"L{index:03d}",
            "text": line,
            "start": round(start, 6),
            "end": round(end, 6),
            "duration": round(frames / TTS_SAMPLE_RATE, 6),
        })

    final_frames = _wav_frames(output_path)
    if final_frames != cursor_frames:
        raise AudioProcessingError(
            "时间轴与最终音频不一致："
            f"分段共 {cursor_frames} 帧，最终 WAV 为 {final_frames} 帧"
        )

    return {
        "line_count": len(timeline),
        "total_duration": round(final_frames / TTS_SAMPLE_RATE, 6),
        "timeline": timeline,
        "output_path": str(output_path),
    }
