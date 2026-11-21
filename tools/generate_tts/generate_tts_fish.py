"""把台词数组合成一条配音（Fish Audio 版）：每段 {text, voice} -> WAV + 时间轴。

与 Edge TTS 版（generate_tts.py）完全独立的第二个 TTS 服务入口：
- voice 传 Fish Audio Voice Library 的 reference_id（支持 "fish:<id>" 前缀写法）；
- API Key 从环境变量 FISH_AUDIO_API_KEY 读取；
- 语速复用 edge 的 "+20%" 倍速写法，内部转成 Fish Audio 的 prosody.speed（0.5-2.0）；
- 时间轴、停顿、响度标准化等后处理与 edge 版语义一致（共用 _pipeline）。
"""

from __future__ import annotations

from pathlib import Path

from ._constants import (
    FISH_AUDIO_CONCURRENCY,
    FISH_VOICE_RATES,
    TTS_BETWEEN_SENTENCE_TRAILING_SECONDS,
    TTS_DEFAULT_RATE,
    TTS_ENDING_PADDING_SECONDS,
)
from ._errors import InvalidParameterError
from ._fish import rate_to_speed, resolve_api_key, resolve_reference_id, synthesize_fish
from ._pipeline import parse_bool, parse_pause, synthesize_pipeline

__all__ = ["generate_tts_fish"]


def _fish_speak(line: dict, raw_path: Path) -> None:
    synthesize_fish(
        line["text"],
        raw_path,
        resolve_reference_id(line["voice"]),
        speed=line["speed"],
    )


def _parse_line(item: object, index: int, default_speed: float) -> dict:
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
        raise InvalidParameterError("script", f"第 {index} 项必须提供 voice（Fish Audio reference_id）")
    if "rate" in item:
        speed = rate_to_speed(item["rate"])
    else:
        # 优先级：行内 rate > 音色绑定语速 > 调用方 rate 参数
        bound_rate = FISH_VOICE_RATES.get(resolve_reference_id(voice).lower())
        speed = rate_to_speed(bound_rate) if bound_rate else default_speed
    return {"text": text, "voice": voice, "speed": speed}


def _parse_script(script: object, default_speed: float) -> list[dict]:
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
    return [_parse_line(item, index, default_speed) for index, item in enumerate(script, 1)]


def generate_tts_fish(
    script: list[dict],
    output_path: str | Path,
    *,
    pause_start: float = 0.0,
    pause_between: float = TTS_BETWEEN_SENTENCE_TRAILING_SECONDS,
    pause_end: float = TTS_ENDING_PADDING_SECONDS,
    rate: str = TTS_DEFAULT_RATE,
    trim_trailing_silence: bool = False,
) -> dict:
    """按数组顺序合成配音（Fish Audio）。单句传长度为 1 的 [{text, voice}]；停顿单位为秒。

    voice 为 Fish Audio reference_id；rate 沿用 edge 倍速写法（"+20%" 等），转 prosody.speed。
    """
    resolve_api_key()  # 提前失败，避免跑到一半才报缺凭据
    default_speed = rate_to_speed(rate)
    lines = _parse_script(script, default_speed)
    return synthesize_pipeline(
        lines,
        _fish_speak,
        Path(output_path),
        pause_start=parse_pause(pause_start, "pause_start", 0.0),
        pause_between=parse_pause(pause_between, "pause_between", TTS_BETWEEN_SENTENCE_TRAILING_SECONDS),
        pause_end=parse_pause(pause_end, "pause_end", TTS_ENDING_PADDING_SECONDS),
        trim_trailing=parse_bool(trim_trailing_silence, "trim_trailing_silence", False),
        concurrency=FISH_AUDIO_CONCURRENCY,
        provider="fish_audio",
    )
