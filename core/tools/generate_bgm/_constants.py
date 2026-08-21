"""生成 BGM 常量：固定音量，按时长循环或裁剪。"""

from __future__ import annotations

from pathlib import Path

_BGM_FILE_DIR = Path(__file__).resolve().parent / "static"


def _p(filename: str) -> Path:
    return (_BGM_FILE_DIR / filename).resolve()


# 财经默认曲目；业务线把这个路径传给 generate_bgm，不再按标签选曲
BGM_CINEMATIC_PIANO_PATH = _p("cinematic-inspirational-piano-ambient-128209.mp3")

BGM_GAIN = 0.28
BGM_FADE_IN_SECONDS = 1.0
BGM_FADE_OUT_SECONDS = 2.0

BGM_AUDIO_CODEC = "aac"
BGM_AUDIO_RATE = 48_000
BGM_AUDIO_CHANNELS = 2
BGM_PROBE_TIMEOUT_SECONDS = 30
BGM_GENERATE_MIN_TIMEOUT_SECONDS = 60
BGM_GENERATE_TIMEOUT_PER_SECOND = 8
