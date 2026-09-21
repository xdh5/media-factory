"""Fish Audio TTS HTTP 调用。

与 edge-tts 完全独立的第二个 TTS 服务实现：
- API Key 从环境变量 FISH_AUDIO_API_KEY 读取；
- 音色传 Voice Library 的 reference_id（如 bc9e47fd83a04010ad6617ed54b92ee3）；
- 语速走请求体 prosody.speed（0.5-2.0），与 edge 的 "+20%" 写法通过 rate_to_speed 互转；
- 响应为二进制音频流（默认 mp3），无 JSON 外壳。
"""

from __future__ import annotations

import os
import re
import threading
import time
from pathlib import Path
from random import uniform

import msgpack
import requests

from ._constants import (
    FISH_AUDIO_API_BASE,
    FISH_AUDIO_CHUNK_LENGTH,
    FISH_AUDIO_CONNECT_TIMEOUT_SECONDS,
    FISH_AUDIO_FORMAT,
    FISH_AUDIO_LATENCY,
    FISH_AUDIO_MAX_ATTEMPTS,
    FISH_AUDIO_MIN_REQUEST_INTERVAL_SECONDS,
    FISH_AUDIO_MODEL,
    FISH_AUDIO_MP3_BITRATE,
    FISH_AUDIO_NORMALIZE,
    FISH_AUDIO_READ_TIMEOUT_SECONDS,
    FISH_AUDIO_RETRY_BASE_SECONDS,
    FISH_AUDIO_RETRY_JITTER_SECONDS,
    FISH_AUDIO_RETRY_MAX_SECONDS,
    FISH_AUDIO_TTS_PATH,
)
from ._errors import EmptyTextError, FishAudioCredentialError, InvalidParameterError, SynthesisError

__all__ = ["rate_to_speed", "resolve_api_key", "resolve_reference_id", "synthesize_fish"]

FISH_VOICE_PREFIX = "fish:"
_REFERENCE_ID_PATTERN = re.compile(r"^[0-9a-fA-F]{32}$")

# Fish Audio 请求节流：相邻请求起始最小间隔，批量台词防限流。
_throttle_lock = threading.Lock()
_last_request_at = 0.0


def _throttle_request() -> None:
    global _last_request_at
    with _throttle_lock:
        wait = FISH_AUDIO_MIN_REQUEST_INTERVAL_SECONDS - (time.monotonic() - _last_request_at)
        if wait > 0:
            time.sleep(wait)
        _last_request_at = time.monotonic()


def resolve_api_key() -> str:
    api_key = (os.getenv("FISH_AUDIO_API_KEY") or "").strip()
    if not api_key:
        raise FishAudioCredentialError(
            "环境变量 FISH_AUDIO_API_KEY 未配置，无法调用 Fish Audio TTS",
            {"env_var": "FISH_AUDIO_API_KEY"},
        )
    return api_key


def resolve_reference_id(voice: str) -> str:
    """接受裸 reference_id 或 "fish:<reference_id>" 前缀写法。"""
    text = (voice or "").strip()
    if text.lower().startswith(FISH_VOICE_PREFIX):
        text = text[len(FISH_VOICE_PREFIX):].strip()
    if not text:
        raise InvalidParameterError("voice", "Fish Audio 音色不能为空（需传 reference_id 或 fish:<reference_id>）")
    return text


def rate_to_speed(rate: str) -> float:
    """edge 倍速写法转 Fish Audio prosody.speed："+20%" -> 1.2，并夹紧到 0.5-2.0。"""
    text = (rate or "").strip() or "+0%"
    match = re.fullmatch(r"([+-])(\d+)%", text)
    if not match:
        raise InvalidParameterError("rate", f"rate 必须是倍速格式（如 +0%、+20%、-10%），当前为 {rate!r}")
    sign = 1 if match.group(1) == "+" else -1
    speed = 1.0 + sign * int(match.group(2)) / 100.0
    return round(min(max(speed, 0.5), 2.0), 4)


def synthesize_fish(text: str, output_path: Path, reference_id: str, *, speed: float = 1.0) -> None:
    """单句走 Fish Audio TTS，写出临时 MP3；只给 generate_tts_fish 内部使用。"""
    text = text.strip()
    if not text:
        raise EmptyTextError("待合成文本为空")
    api_key = resolve_api_key()
    model = (os.getenv("FISH_AUDIO_MODEL") or FISH_AUDIO_MODEL).strip()
    payload: dict = {
        "text": text,
        "reference_id": reference_id,
        "format": FISH_AUDIO_FORMAT,
        "mp3_bitrate": FISH_AUDIO_MP3_BITRATE,
        "chunk_length": FISH_AUDIO_CHUNK_LENGTH,
        "latency": FISH_AUDIO_LATENCY,
        "normalize": FISH_AUDIO_NORMALIZE,
    }
    if abs(speed - 1.0) > 1e-6:
        payload["prosody"] = {"speed": speed, "volume": 0}
    body = msgpack.packb(payload, use_bin_type=True)
    headers = {
        "Authorization": f"Bearer {api_key}",
        "Content-Type": "application/msgpack",
        "model": model,
        "User-Agent": "media-factory/1.0",
    }
    url = FISH_AUDIO_API_BASE + FISH_AUDIO_TTS_PATH
    temporary_output = output_path.with_name(f".{output_path.name}.part")
    last_error: Exception | None = None
    for attempt in range(1, FISH_AUDIO_MAX_ATTEMPTS + 1):
        audio_bytes = 0
        try:
            _throttle_request()
            temporary_output.unlink(missing_ok=True)
            with requests.post(
                url,
                data=body,
                headers=headers,
                stream=True,
                timeout=(FISH_AUDIO_CONNECT_TIMEOUT_SECONDS, FISH_AUDIO_READ_TIMEOUT_SECONDS),
            ) as response:
                if response.status_code != 200:
                    detail = response.text[:300]
                    raise RuntimeError(f"HTTP {response.status_code}: {detail}")
                with temporary_output.open("wb") as target:
                    for chunk in response.iter_content(chunk_size=64 * 1024):
                        if chunk:
                            target.write(chunk)
                            audio_bytes += len(chunk)
            if audio_bytes <= 0:
                raise RuntimeError("Fish Audio 未返回任何音频数据")
            temporary_output.replace(output_path)
            return
        except Exception as exc:
            last_error = exc
            temporary_output.unlink(missing_ok=True)
            if attempt == FISH_AUDIO_MAX_ATTEMPTS:
                raise SynthesisError(
                    f"Fish Audio TTS 连续尝试 {FISH_AUDIO_MAX_ATTEMPTS} 次仍失败："
                    f"{type(exc).__name__}: {exc}",
                    {
                        "attempts": FISH_AUDIO_MAX_ATTEMPTS,
                        "exception_type": type(exc).__name__,
                        "reference_id": reference_id,
                        "model": model,
                    },
                ) from exc
            retry_delay = min(
                FISH_AUDIO_RETRY_BASE_SECONDS * (2 ** (attempt - 1)),
                FISH_AUDIO_RETRY_MAX_SECONDS,
            ) + uniform(0.0, FISH_AUDIO_RETRY_JITTER_SECONDS)
            time.sleep(retry_delay)
    raise SynthesisError(f"Fish Audio TTS 合成失败：{last_error}")
