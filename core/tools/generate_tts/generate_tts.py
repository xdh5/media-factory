"""把台词数组合成一条配音：每段 {text, voice} -> WAV + 时间轴。"""

from __future__ import annotations

import asyncio
import re
import shutil
import subprocess
import tempfile
import threading
import wave
from concurrent.futures import ThreadPoolExecutor, as_completed
from pathlib import Path
from random import uniform

import edge_tts

from ._constants import (
    TTS_BETWEEN_SENTENCE_TRAILING_SECONDS,
    TTS_CHANNELS,
    TTS_CONCURRENCY,
    TTS_CONNECT_TIMEOUT_SECONDS,
    TTS_DEFAULT_RATE,
    TTS_ENDING_PADDING_SECONDS,
    TTS_LRA,
    TTS_MAX_ATTEMPTS,
    TTS_RECEIVE_TIMEOUT_SECONDS,
    TTS_RETRY_BASE_SECONDS,
    TTS_RETRY_JITTER_SECONDS,
    TTS_RETRY_MAX_SECONDS,
    TTS_SAMPLE_RATE,
    TTS_SILENCE_DETECTION_SECONDS,
    TTS_SILENCE_KEEP_COMPENSATION_SECONDS,
    TTS_SILENCE_THRESHOLD_DB,
    TTS_TARGET_LUFS,
    TTS_TRUE_PEAK_DB,
    TTS_VOICES,
)
from ._errors import (
    AudioProcessingError,
    EmptyTextError,
    FFmpegNotFoundError,
    InvalidOutputPathError,
    InvalidParameterError,
    SynthesisError,
    UnsupportedVoiceError,
)
from ._normalize_loudness import _normalize_loudness

__all__ = ["generate_tts"]


TTS_RATE_PATTERN = re.compile(r"^[+-]\d+%$")


def _resolve_voice(voice: str) -> str:
    for item in TTS_VOICES:
        if voice in (item["id"], item["name"]):
            return item["id"]
    raise UnsupportedVoiceError(voice, TTS_VOICES)


def _parse_rate(value: object, parameter: str = "rate") -> str:
    if value is None:
        return TTS_DEFAULT_RATE
    text = str(value).strip()
    if not TTS_RATE_PATTERN.fullmatch(text):
        raise InvalidParameterError(
            parameter,
            f"{parameter} 必须是 Edge TTS 倍速格式，例如 +0%、+20%、-10%",
        )
    return text


async def _speak(text: str, output_path: Path, voice: str, rate: str) -> None:
    """单句走 Edge TTS，写出临时 MP3；只给 generate_tts 内部用。"""
    text = text.strip()
    if not text:
        raise EmptyTextError("待合成文本为空")
    voice_name = _resolve_voice(voice)
    temporary_output = output_path.with_name(f".{output_path.name}.part")
    last_error: Exception | None = None
    for attempt in range(1, TTS_MAX_ATTEMPTS + 1):
        audio_bytes = 0
        try:
            temporary_output.unlink(missing_ok=True)
            communicate = edge_tts.Communicate(
                text,
                voice_name,
                rate=rate,
                boundary="WordBoundary",
                connect_timeout=TTS_CONNECT_TIMEOUT_SECONDS,
                receive_timeout=TTS_RECEIVE_TIMEOUT_SECONDS,
            )
            with temporary_output.open("wb") as target:
                async for chunk in communicate.stream():
                    if chunk["type"] == "audio":
                        target.write(chunk["data"])
                        audio_bytes += len(chunk["data"])
            if audio_bytes <= 0:
                raise RuntimeError("Edge TTS 未返回任何音频数据")
            temporary_output.replace(output_path)
            return
        except Exception as exc:
            last_error = exc
            temporary_output.unlink(missing_ok=True)
            if attempt == TTS_MAX_ATTEMPTS:
                raise SynthesisError(
                    f"TTS 连续尝试 {TTS_MAX_ATTEMPTS} 次仍失败：{type(exc).__name__}: {exc}",
                    {"attempts": TTS_MAX_ATTEMPTS, "exception_type": type(exc).__name__},
                ) from exc
            retry_delay = min(
                TTS_RETRY_BASE_SECONDS * (2 ** (attempt - 1)),
                TTS_RETRY_MAX_SECONDS,
            ) + uniform(0.0, TTS_RETRY_JITTER_SECONDS)
            await asyncio.sleep(retry_delay)
    raise SynthesisError(f"TTS 合成失败：{last_error}")


def _parse_line(item: object, index: int, default_rate: str) -> dict:
    if not isinstance(item, dict):
        raise InvalidParameterError("script", f"第 {index} 项必须是对象，且包含 text 和 voice")
    unknown = sorted(set(item) - {"text", "voice", "rate"})
    if unknown:
        raise InvalidParameterError("script", f"第 {index} 项含未知字段 {unknown}，只允许 text、voice、rate")
    text = str(item.get("text") or "").strip()
    voice = str(item.get("voice") or "").strip()
    if not text:
        raise InvalidParameterError("script", f"第 {index} 项 text 不能为空")
    if not voice:
        raise InvalidParameterError("script", f"第 {index} 项必须提供 voice")
    rate = _parse_rate(item["rate"], f"script[{index}].rate") if "rate" in item else default_rate
    return {"text": text, "voice": voice, "rate": rate}


def _parse_script(script: object, default_rate: str) -> list[dict]:
    if isinstance(script, str):
        raise InvalidParameterError(
            "script",
            "script 必须是非空数组，每一项为 {text, voice}；单句也传长度为 1 的数组",
        )
    if not isinstance(script, list) or not script:
        raise InvalidParameterError(
            "script",
            "script 必须是非空数组，每一项为 {text, voice}；单句也传长度为 1 的数组",
        )
    return [_parse_line(item, index, default_rate) for index, item in enumerate(script, 1)]


def _wav_frames(path: Path) -> int:
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


def _pause_seconds(value: object, parameter: str, default: float) -> float:
    if value is None:
        return default
    try:
        number = float(value)
    except (TypeError, ValueError) as exc:
        raise InvalidParameterError(parameter, f"{parameter} 必须是非负数") from exc
    if number < 0:
        raise InvalidParameterError(parameter, f"{parameter} 不能小于 0")
    return number


def _concat_wavs(ffmpeg: str, sources: list[Path], output: Path, context: str) -> None:
    manifest = output.with_suffix(".txt")
    manifest.write_text(
        "".join(f"file '{path.as_posix()}'\n" for path in sources),
        encoding="utf-8",
    )
    _run_ffmpeg(
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
    _run_ffmpeg(
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


def _parse_bool(value: object, parameter: str, default: bool) -> bool:
    if value is None:
        return default
    if isinstance(value, bool):
        return value
    raise InvalidParameterError(parameter, f"{parameter} 必须是布尔值")


def generate_tts(
    script: list[dict],
    output_path: str | Path,
    *,
    pause_start: float = 0.0,
    pause_between: float = TTS_BETWEEN_SENTENCE_TRAILING_SECONDS,
    pause_end: float = TTS_ENDING_PADDING_SECONDS,
    rate: str = TTS_DEFAULT_RATE,
    trim_trailing_silence: bool = False,
) -> dict:
    """按数组顺序合成配音。单句传长度为 1 的 [{text, voice}]；停顿单位为秒。不传 rate 为原速。"""
    default_rate = _parse_rate(rate, "rate")
    lines = _parse_script(script, default_rate)
    start_silence = _pause_seconds(pause_start, "pause_start", 0.0)
    between_silence = _pause_seconds(pause_between, "pause_between", TTS_BETWEEN_SENTENCE_TRAILING_SECONDS)
    end_silence = _pause_seconds(pause_end, "pause_end", TTS_ENDING_PADDING_SECONDS)
    trim_trailing = _parse_bool(trim_trailing_silence, "trim_trailing_silence", False)

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
                asyncio.run(_speak(line["text"], raw_path, line["voice"], line["rate"]))
            except Exception as exc:
                raise SynthesisError(
                    f"第 {index} 行 TTS 合成失败：{exc}",
                    {"line_index": index, "text_preview": line["text"][:80], "voice": line["voice"]},
                ) from exc
            if cancel_pending.is_set():
                raise AudioProcessingError(f"第 {index} 行因其他台词合成失败而取消")
            trailing = end_silence if index == len(lines) else between_silence
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
            _run_ffmpeg(
                ffmpeg,
                convert,
                f"第 {index} 行静音处理失败" if trim_trailing else f"第 {index} 行转码失败",
            )
            pieces = []
            if index == 1 and start_silence > 0:
                pieces.append(_silence_wav(ffmpeg, temporary_dir / "pause-start.wav", start_silence))
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
            frames = _wav_frames(line_path)
            if frames <= 0:
                raise AudioProcessingError(f"第 {index} 行处理后没有可用音频")
            return {"audio_path": str(line_path), "frames": frames}

        first_error: Exception | None = None
        executor = ThreadPoolExecutor(
            max_workers=min(TTS_CONCURRENCY, len(lines)),
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
        _run_ffmpeg(
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
        timeline.append({
            "id": f"L{index:03d}",
            "text": line["text"],
            "voice": line["voice"],
            "rate": line["rate"],
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
        "pause_start": start_silence,
        "pause_between": between_silence,
        "pause_end": end_silence,
        "rate": default_rate,
        "trim_trailing_silence": trim_trailing,
        "loudness": loudness,
    }
