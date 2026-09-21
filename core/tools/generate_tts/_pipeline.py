"""generate_tts（edge-tts）与 generate_tts_fish（Fish Audio）共用的音频流水线。

两个 TTS 服务的方法彼此完全独立（各自的 speak 实现各自处理音色、语速、重试与限流），
本模块只负责共同的后处理编排：
单句并行合成 -> ffmpeg 转码/尾部静音裁剪 -> 停顿拼接 -> 整体拼接 -> 响度标准化 -> 时间轴。
"""

from __future__ import annotations

import shutil
import tempfile
import threading
import wave
from concurrent.futures import ThreadPoolExecutor, as_completed
from pathlib import Path
from typing import Callable

from ._constants import (
    TTS_BETWEEN_SENTENCE_TRAILING_SECONDS,
    TTS_CHANNELS,
    TTS_CONCURRENCY,
    TTS_ENDING_PADDING_SECONDS,
    TTS_SAMPLE_RATE,
    TTS_SILENCE_DETECTION_SECONDS,
    TTS_SILENCE_KEEP_COMPENSATION_SECONDS,
    TTS_SILENCE_THRESHOLD_DB,
    TTS_TARGET_LUFS,
    TTS_LRA,
    TTS_TRUE_PEAK_DB,
)
from ._errors import (
    AudioProcessingError,
    FFmpegNotFoundError,
    InvalidOutputPathError,
    InvalidParameterError,
    SynthesisError,
)
from ._normalize_loudness import _normalize_loudness

__all__ = [
    "Speaker",
    "parse_bool",
    "parse_pause",
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


def parse_pause(value: object, parameter: str, default: float) -> float:
    if value is None:
        return default
    try:
        number = float(value)
    except (TypeError, ValueError) as exc:
        raise AudioProcessingError(f"{parameter} 必须是非负数") from exc
    if number < 0:
        raise AudioProcessingError(f"{parameter} 不能小于 0")
    return number


def parse_bool(value: object, parameter: str, default: bool) -> bool:
    if value is None:
        return default
    if isinstance(value, bool):
        return value
    raise AudioProcessingError(f"{parameter} 必须是布尔值")


def _concat_wavs(ffmpeg: str, sources: list[Path], output: Path, context: str) -> None:
    manifest = output.with_suffix(".txt")
    manifest.write_text(
        "".join(f"file '{path.as_posix()}'\n" for path in sources),
        encoding="utf-8",
    )
    run_ffmpeg(
        ffmpeg,
        [
            "-f", "concat", "-safe", "0", "-i", str(manifest),
            "-vn",
            "-ac", str(TTS_CHANNELS),
            "-ar", str(TTS_SAMPLE_RATE),
            "-c:a", "pcm_s16le",
            str(output),
        ],
        context,
    )
    manifest.unlink(missing_ok=True)


def _silence_wav(ffmpeg: str, path: Path, seconds: float) -> Path:
    run_ffmpeg(
        ffmpeg,
        [
            "-f", "lavfi",
            "-t", f"{seconds:.9f}",
            "-i", f"anullsrc=r={TTS_SAMPLE_RATE}:cl=mono",
            "-ac", str(TTS_CHANNELS),
            "-ar", str(TTS_SAMPLE_RATE),
            "-c:a", "pcm_s16le",
            str(path),
        ],
        "生成静音失败",
    )
    return path


def synthesize_pipeline(
    lines: list[dict],
    speak: Speaker,
    output_path: Path,
    *,
    pause_start: float = 0.0,
    pause_between: float = TTS_BETWEEN_SENTENCE_TRAILING_SECONDS,
    pause_end: float = TTS_ENDING_PADDING_SECONDS,
    trim_trailing: bool = False,
    concurrency: int = TTS_CONCURRENCY,
    provider: str,
) -> dict:
    """按数组顺序合成配音。单句传长度为 1 的 [{text, voice}]；停顿单位为秒。"""
    output_path = Path(output_path)
    if output_path.suffix.lower() != ".wav":
        raise InvalidOutputPathError(str(output_path))
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
            raw_path = temporary_dir / f"line-{index:04d}.mp3"
            speech_path = temporary_dir / f"line-{index:04d}-speech.wav"
            try:
                speak(line, raw_path)
            except Exception as exc:
                raise SynthesisError(
                    f"第 {index} 行 TTS 合成失败：{exc}",
                    {"line_index": index, "text_preview": line["text"][:80], "voice": line["voice"]},
                ) from exc
            if cancel_pending.is_set():
                raise AudioProcessingError(f"第 {index} 行因其他台词合成失败而取消")
            trailing = pause_end if index == len(lines) else pause_between
            convert = [
                "-i", str(raw_path),
                "-ac", str(TTS_CHANNELS),
                "-ar", str(TTS_SAMPLE_RATE),
                "-c:a", "pcm_s16le",
                str(speech_path),
            ]
            if trim_trailing:
                retained_silence = trailing + TTS_SILENCE_KEEP_COMPENSATION_SECONDS
                convert[2:2] = [
                    "-af",
                    (
                        "areverse,"
                        "silenceremove="
                        f"start_periods=1:start_duration={TTS_SILENCE_DETECTION_SECONDS:.3f}:"
                        f"start_threshold={TTS_SILENCE_THRESHOLD_DB:.1f}dB:"
                        f"start_silence={retained_silence:.3f},"
                        "areverse"
                    ),
                ]
            run_ffmpeg(
                ffmpeg,
                convert,
                f"第 {index} 行静音处理失败" if trim_trailing else f"第 {index} 行转码失败",
            )
            pieces = []
            if index == 1 and pause_start > 0:
                pieces.append(_silence_wav(ffmpeg, temporary_dir / "pause-start.wav", pause_start))
            pieces.append(speech_path)
            if not trim_trailing and trailing > 0:
                pieces.append(
                    _silence_wav(ffmpeg, temporary_dir / f"pause-{index:04d}.wav", trailing)
                )
            line_path = temporary_dir / f"line-{index:04d}.wav"
            if len(pieces) == 1:
                speech_path.replace(line_path)
            else:
                _concat_wavs(ffmpeg, pieces, line_path, f"第 {index} 行拼接停顿失败")
            frames = wav_frames(line_path)
            if frames <= 0:
                raise AudioProcessingError(f"第 {index} 行处理后没有可用音频")
            return {"audio_path": str(line_path), "frames": frames}

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

        concat_file = temporary_dir / "segments.txt"
        concat_path = temporary_dir / "concat.wav"
        concat_file.write_text(
            "".join(f"file '{Path(seg['audio_path']).as_posix()}'\n" for seg in segments),
            encoding="utf-8",
        )
        run_ffmpeg(
            ffmpeg,
            [
                "-f", "concat", "-safe", "0", "-i", str(concat_file),
                "-vn",
                "-ac", str(TTS_CHANNELS),
                "-ar", str(TTS_SAMPLE_RATE),
                "-c:a", "pcm_s16le",
                str(concat_path),
            ],
            "拼接完整配音失败",
        )
        loudness = _normalize_loudness(
            concat_path,
            output_path,
            target_lufs=TTS_TARGET_LUFS,
            true_peak_db=TTS_TRUE_PEAK_DB,
            lra=TTS_LRA,
        )

    timeline: list[dict] = []
    cursor_frames = 0
    for index, (line, seg) in enumerate(zip(lines, segments), 1):
        frames = seg["frames"]
        start = cursor_frames / TTS_SAMPLE_RATE
        cursor_frames += frames
        end = cursor_frames / TTS_SAMPLE_RATE
        extras = {key: value for key, value in line.items() if key not in ("text", "voice")}
        timeline.append({
            "id": f"L{index:03d}",
            "text": line["text"],
            "voice": line["voice"],
            **extras,
            "start": round(start, 6),
            "end": round(end, 6),
            "duration": round(frames / TTS_SAMPLE_RATE, 6),
        })

    final_frames = wav_frames(output_path)
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
        "pause_start": pause_start,
        "pause_between": pause_between,
        "pause_end": pause_end,
        "trim_trailing_silence": trim_trailing,
        "loudness": loudness,
        "provider": provider,
    }
