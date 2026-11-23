"""generate_tts（edge-tts）与 generate_tts_fish（Fish Audio）共用的音频流水线。

两个 TTS 服务的方法彼此完全独立（各自的 speak 实现各自处理音色、语速与限流），
本模块只负责共同的后处理编排：
分段并行合成 -> 原格式拼接 -> 时间轴。
"""

from __future__ import annotations

import shutil
import sys
import json
import subprocess
import tempfile
import threading
import wave
from concurrent.futures import ThreadPoolExecutor, as_completed
from pathlib import Path
from typing import Callable

from ._constants import (
    TTS_CHANNELS,
    TTS_CONCURRENCY,
    TTS_SAMPLE_RATE,
)
from ._errors import (
    AudioProcessingError,
    FFmpegNotFoundError,
    InvalidOutputPathError,
    InvalidParameterError,
    SynthesisError,
)

__all__ = [
    "Speaker",
    "run_ffmpeg",
    "synthesize_pipeline",
    "wav_frames",
]

# speak(line, raw_path)：单句合成，line 为解析后的台词 dict（text/voice/语速字段由各服务自定），
# raw_path 为原始音频（mp3）输出路径。
Speaker = Callable[[dict, Path], None]


def wav_frames(path: Path) -> int:
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


def run_ffmpeg(ffmpeg: str, command: list[str], context: str) -> None:
    import subprocess

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


def synthesize_pipeline(
    lines: list[dict],
    speak: Speaker,
    output_path: Path,
    *,
    concurrency: int = TTS_CONCURRENCY,
    provider: str,
) -> dict:
    """按数组顺序合成配音。单句传长度为 1 的 [{text, voice}]；停顿单位为秒。"""
    output_path = Path(output_path)
    if output_path.suffix.lower() != ".wav":
        raise InvalidOutputPathError(str(output_path))
    output_path = output_path.with_suffix('.wav' if provider == 'azure' else '.mp3')
    output_path.parent.mkdir(parents=True, exist_ok=True)
    ffmpeg = shutil.which("ffmpeg")
    if not ffmpeg:
        raise FFmpegNotFoundError()

    with tempfile.TemporaryDirectory(prefix="tts-generate-") as temporary:
        temporary_dir = Path(temporary)
        segments: list[dict | None] = [None] * len(lines)
        cancel_pending = threading.Event()

        def _synthesize_line(index: int, line: dict) -> dict:
            if cancel_pending.is_set():
                raise AudioProcessingError(f"第 {index} 行因其他台词合成失败而取消")
            raw_path = temporary_dir / f"line-{index:04d}{output_path.suffix}"
            try:
                speak(line, raw_path)
            except Exception as exc:
                raise SynthesisError(
                    f"第 {index} 行 TTS 合成失败：{exc}",
                    {"line_index": index, "text_preview": line["text"][:80], "voice": line["voice"]},
                ) from exc
            if cancel_pending.is_set():
                raise AudioProcessingError(f"第 {index} 行因其他台词合成失败而取消")
            probe = subprocess.run(
                [shutil.which('ffprobe') or 'ffprobe', '-v', 'error', '-show_entries',
                 'format=duration', '-of', 'json', str(raw_path)],
                capture_output=True, text=True, check=True,
            )
            duration = float(json.loads(probe.stdout)['format']['duration'])
            return {'audio_path': str(raw_path), 'duration': duration}

        first_error: Exception | None = None
        executor = ThreadPoolExecutor(
            max_workers=max(1, min(concurrency, len(lines))),
            thread_name_prefix="tts-generate",
        )
        try:
            futures = {
                executor.submit(_synthesize_line, index, line): index - 1
                for index, line in enumerate(lines, 1)
            }
            for future in as_completed(futures):
                try:
                    segments[futures[future]] = future.result()
                except Exception as exc:
                    first_error = exc
                    cancel_pending.set()
                    for pending in futures:
                        if pending is not future:
                            pending.cancel()
                    break
        finally:
            executor.shutdown(wait=True, cancel_futures=True)
        if first_error:
            raise first_error

        if provider == 'azure':
            with wave.open(str(output_path), 'wb') as target:
                with wave.open(segments[0]['audio_path'], 'rb') as first:
                    target.setparams(first.getparams())
                for segment in segments:
                    with wave.open(segment['audio_path'], 'rb') as source:
                        target.writeframes(source.readframes(source.getnframes()))
        else:
            concat_file = temporary_dir / 'segments.txt'
            concat_file.write_text(
                ''.join(f"file '{Path(segment['audio_path']).as_posix()}'\n" for segment in segments),
                encoding='utf-8',
            )
            run_ffmpeg(ffmpeg, ['-f', 'concat', '-safe', '0', '-i', str(concat_file),
                               '-c:a', 'copy', str(output_path)], '拼接原始配音失败')

    timeline: list[dict] = []
    cursor = 0.0
    for index, (line, seg) in enumerate(zip(lines, segments), 1):
        start = cursor
        cursor += seg["duration"]
        end = cursor
        extras = {key: value for key, value in line.items() if key not in ("text", "voice")}
        timeline.append({
            "id": f"L{index:03d}",
            "text": line["text"],
            "voice": line["voice"],
            **extras,
            "start": round(start, 6),
            "end": round(end, 6),
            "duration": round(seg["duration"], 6),
        })

    return {
        "line_count": len(timeline),
        "total_duration": round(cursor, 6),
        "timeline": timeline,
        "output_path": str(output_path),
        "provider": provider,
    }
