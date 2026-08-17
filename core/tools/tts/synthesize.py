"""edge-tts 封装：文本转 mp3 录音，供 agent 调用，返回 JSON 友好的 dict。"""

from __future__ import annotations

import asyncio
from pathlib import Path

import edge_tts

from core.tools.tts._constants import TTS_RATES, TTS_VOICES
from core.tools.tts._errors import EmptyTextError, SynthesisError, UnsupportedVoiceError

__all__ = ["synthesize"]

# 网络超时（秒）、最大尝试次数、重试间隔（秒）
CONNECT_TIMEOUT = 10
RECEIVE_TIMEOUT = 60
MAX_ATTEMPTS = 2
RETRY_DELAY = 1.0


def _resolve(voice: str) -> tuple[str, str]:
    """按音色查表，返回 (完整音色 id, 倍速)。语言由音色自带，倍速按语言查。"""
    for v in TTS_VOICES:
        if voice in (v["id"], v["name"]):
            return v["id"], TTS_RATES[v["language"].split("-")[0]]
    raise UnsupportedVoiceError(voice, TTS_VOICES)


async def synthesize(
    text: str,
    output_path: str | Path,
    voice: str,
) -> dict:
    """把文本合成为一个 mp3 文件，返回 dict（可直接 json.dumps）：
    {"text": 原文本, "audio_path": 音频文件路径, "duration": 语音时长秒}

    voice: 音色 id 或 name，如 "Xiaoxiao" / "zh-CN-XiaoxiaoNeural"，语言由音色决定
    """
    text = text.strip()
    if not text:
        raise EmptyTextError("待合成文本为空")

    output_path = Path(output_path)
    output_path.parent.mkdir(parents=True, exist_ok=True)

    voice_name, rate = _resolve(voice)

    duration = 0.0  # 最后一个词的结束时间，即语音时长（不含尾部静音）
    for attempt in range(1, MAX_ATTEMPTS + 1):
        try:
            communicate = edge_tts.Communicate(
                text,
                voice_name,
                rate=rate,
                boundary="WordBoundary",
                connect_timeout=CONNECT_TIMEOUT,
                receive_timeout=RECEIVE_TIMEOUT,
            )
            duration = 0.0
            with open(output_path, "wb") as f:
                async for chunk in communicate.stream():
                    if chunk["type"] == "audio":
                        f.write(chunk["data"])
                    elif chunk["type"] == "WordBoundary":
                        duration = (chunk["offset"] + chunk["duration"]) / 1e7
            break
        except Exception as e:  # 网络抖动等，重试一次
            if attempt == MAX_ATTEMPTS:
                raise SynthesisError(f"TTS 合成失败：{e}") from e
            await asyncio.sleep(RETRY_DELAY)

    return {"text": text, "audio_path": str(output_path), "duration": round(duration, 3)}
