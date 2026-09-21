"""把台词数组合成一条配音（Edge TTS 版）：每段 {text, voice} -> WAV + 时间轴。

Fish Audio 版本见 generate_tts_fish.py，两个服务的方法彼此独立。
"""

from __future__ import annotations

import asyncio
import re
import time
import threading
from pathlib import Path
from random import uniform

import edge_tts

from ._constants import (
    TTS_BETWEEN_SENTENCE_TRAILING_SECONDS,
    TTS_CONCURRENCY,
    TTS_CONNECT_TIMEOUT_SECONDS,
    TTS_DEFAULT_RATE,
    TTS_ENDING_PADDING_SECONDS,
    TTS_MAX_ATTEMPTS,
    TTS_MIN_REQUEST_INTERVAL_SECONDS,
    TTS_RECEIVE_TIMEOUT_SECONDS,
    TTS_RETRY_BASE_SECONDS,
    TTS_RETRY_JITTER_SECONDS,
    TTS_RETRY_MAX_SECONDS,
    TTS_VOICES,
)
from ._errors import (
    EmptyTextError,
    InvalidParameterError,
    SynthesisError,
    UnsupportedVoiceError,
)
from ._pipeline import parse_bool, parse_pause, synthesize_pipeline

__all__ = ["generate_tts"]


TTS_RATE_PATTERN = re.compile(r"^[+-]\d+%$")


def _resolve_voice(voice: str) -> str:
    for item in TTS_VOICES:
        if voice in (item["id"], item["name"]):
            return item["id"]
    raise UnsupportedVoiceError(voice, TTS_VOICES)


# 全局请求节流：相邻合成请求的起始间隔不小于 TTS_MIN_REQUEST_INTERVAL_SECONDS。
# Edge TTS 会对短时间内的批量请求限流（返回空音频），并发线程共享这一个节拍器。
_tts_throttle_lock = threading.Lock()
_tts_last_request_at = 0.0


def _throttle_request() -> None:
    global _tts_last_request_at
    with _tts_throttle_lock:
        wait = TTS_MIN_REQUEST_INTERVAL_SECONDS - (time.monotonic() - _tts_last_request_at)
        if wait > 0:
            time.sleep(wait)
        _tts_last_request_at = time.monotonic()


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
            _throttle_request()
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


def _edge_speak(line: dict, raw_path: Path) -> None:
    asyncio.run(_speak(line["text"], raw_path, line["voice"], line["rate"]))


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
    """按数组顺序合成配音（Edge TTS）。单句传长度为 1 的 [{text, voice}]；停顿单位为秒。不传 rate 为原速。"""
    default_rate = _parse_rate(rate, "rate")
    lines = _parse_script(script, default_rate)
    return synthesize_pipeline(
        lines,
        _edge_speak,
        Path(output_path),
        pause_start=parse_pause(pause_start, "pause_start", 0.0),
        pause_between=parse_pause(pause_between, "pause_between", TTS_BETWEEN_SENTENCE_TRAILING_SECONDS),
        pause_end=parse_pause(pause_end, "pause_end", TTS_ENDING_PADDING_SECONDS),
        trim_trailing=parse_bool(trim_trailing_silence, "trim_trailing_silence", False),
        concurrency=TTS_CONCURRENCY,
        provider="edge",
    )
