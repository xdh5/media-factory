"""对 PCM WAV 做响度标准化，仅供 generate_tts 内部使用，并严格保持采样帧数。"""

from __future__ import annotations

import hashlib
import json
import os
import shutil
import subprocess
import wave
from pathlib import Path
from uuid import uuid4

from ._constants import TTS_LOUDNESS_CACHE_VERSION
from ._errors import FFmpegNotFoundError, InvalidParameterError, LoudnessNormalizationError


def _audio_info(path: Path) -> tuple[int, int, int]:
    try:
        with wave.open(str(path), "rb") as audio:
            if audio.getcomptype() != "NONE":
                raise InvalidParameterError("input_path", "只支持未压缩 PCM WAV")
            return audio.getframerate(), audio.getnchannels(), audio.getnframes()
    except InvalidParameterError:
        raise
    except (OSError, EOFError, wave.Error) as exc:
        raise InvalidParameterError("input_path", f"无法读取 PCM WAV：{path}") from exc


def _hash_file(path: Path) -> str:
    digest = hashlib.sha256()
    with path.open("rb") as source:
        for chunk in iter(lambda: source.read(1024 * 1024), b""):
            digest.update(chunk)
    return digest.hexdigest()


def _normalize_loudness(
    input_path: str | Path,
    output_path: str | Path,
    *,
    target_lufs: float,
    true_peak_db: float,
    lra: float,
) -> dict:
    """标准化完整音轨；输出与输入保持相同采样率、声道数和总采样帧数。"""
    source = Path(input_path).resolve()
    output = Path(output_path).resolve()
    if not source.is_file():
        raise InvalidParameterError("input_path", f"输入音频不存在：{source}")
    if source.suffix.lower() != ".wav" or output.suffix.lower() != ".wav":
        raise InvalidParameterError("output_path", "input_path 和 output_path 都必须是 .wav 文件")
    if source == output:
        raise InvalidParameterError("output_path", "output_path 必须与 input_path 不同")
    try:
        target = float(target_lufs)
        peak = float(true_peak_db)
        range_value = float(lra)
    except (TypeError, ValueError) as exc:
        raise InvalidParameterError("target_lufs", "target_lufs、true_peak_db 和 lra 必须是数字") from exc
    if not -70 <= target <= -5:
        raise InvalidParameterError("target_lufs", "target_lufs 必须在 -70～-5 之间")
    if not -9 <= peak <= 0:
        raise InvalidParameterError("true_peak_db", "true_peak_db 必须在 -9～0 之间")
    if not 1 <= range_value <= 50:
        raise InvalidParameterError("lra", "lra 必须在 1～50 之间")
    sample_rate, channels, frames = _audio_info(source)
    signature_payload = {
        "version": TTS_LOUDNESS_CACHE_VERSION,
        "input_sha256": _hash_file(source),
        "target_lufs": target,
        "true_peak_db": peak,
        "lra": range_value,
        "sample_rate": sample_rate,
        "channels": channels,
        "frames": frames,
    }
    signature = hashlib.sha256(
        json.dumps(signature_payload, sort_keys=True, separators=(",", ":")).encode("utf-8")
    ).hexdigest()
    metadata_path = output.with_suffix(".loudness.json")
    if output.is_file() and metadata_path.is_file():
        try:
            metadata = json.loads(metadata_path.read_text(encoding="utf-8"))
            output_info = _audio_info(output)
            if metadata.get("signature") == signature and output_info == (sample_rate, channels, frames):
                return {
                    "output_path": str(output), "target_lufs": target, "true_peak_db": peak,
                    "lra": range_value, "sample_rate": sample_rate, "channels": channels,
                    "frames": frames, "duration": round(frames / sample_rate, 6), "cache_hit": True,
                }
        except (OSError, ValueError, json.JSONDecodeError, InvalidParameterError):
            pass
    ffmpeg = shutil.which("ffmpeg")
    if not ffmpeg:
        raise FFmpegNotFoundError()
    output.parent.mkdir(parents=True, exist_ok=True)
    temporary = output.with_name(f".{output.stem}-{uuid4().hex}.tmp.wav")
    audio_filter = (
        f"loudnorm=I={target}:TP={peak}:LRA={range_value},"
        f"aresample={sample_rate},apad,atrim=end_sample={frames},asetpts=N/SR/TB"
    )
    completed = subprocess.run(
        [
            ffmpeg, "-y", "-i", str(source), "-af", audio_filter,
            "-ac", str(channels), "-ar", str(sample_rate), "-c:a", "pcm_s16le", str(temporary),
        ],
        check=False,
        capture_output=True,
        text=True,
        encoding="utf-8",
        errors="replace",
    )
    if completed.returncode != 0:
        temporary.unlink(missing_ok=True)
        detail = (completed.stderr or completed.stdout or "").strip()[-2000:]
        raise LoudnessNormalizationError(f"响度标准化失败：{detail or '未知 FFmpeg 错误'}")
    if _audio_info(temporary) != (sample_rate, channels, frames):
        temporary.unlink(missing_ok=True)
        raise LoudnessNormalizationError("响度标准化改变了音频采样帧数，已拒绝输出")
    os.replace(temporary, output)
    metadata_path.write_text(
        json.dumps({"signature": signature, **signature_payload}, ensure_ascii=False, sort_keys=True),
        encoding="utf-8",
    )
    return {
        "output_path": str(output), "target_lufs": target, "true_peak_db": peak,
        "lra": range_value, "sample_rate": sample_rate, "channels": channels,
        "frames": frames, "duration": round(frames / sample_rate, 6), "cache_hit": False,
    }
