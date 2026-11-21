"""生成配音公开入口：台词数组合成 WAV 与时间轴（Edge TTS / Fish Audio 两个独立服务）。"""

from .generate_tts import generate_tts
from .generate_tts_fish import generate_tts_fish

__all__ = ["generate_tts", "generate_tts_fish"]
