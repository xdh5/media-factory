"""TTS 错误定义。

错误带 code / message / details，to_dict() 输出 JSON 友好结构，
MCP 工具层捕获后可直接序列化返回给 agent：
    {"error": {"code": "UNSUPPORTED_VOICE", "message": "...", "details": {...}}}
"""

from __future__ import annotations

__all__ = [
    "TTSError",
    "EmptyTextError",
    "UnsupportedVoiceError",
    "SynthesisError",
    "InvalidOutputPathError",
    "FFmpegNotFoundError",
    "AudioProcessingError",
]


class TTSError(Exception):
    """TTS 错误基类。子类通过 code 声明错误码。"""

    code = "TTS_ERROR"

    def __init__(self, message: str, details: dict | None = None):
        super().__init__(message)
        self.message = message
        self.details = details or {}

    def to_dict(self) -> dict:
        return {"error": {"code": self.code, "message": self.message, "details": self.details}}


class EmptyTextError(TTSError):
    """待合成文本为空。"""

    code = "EMPTY_TEXT"


class UnsupportedVoiceError(TTSError):
    """音色不在音色库里。details.supported_voices 列出全部可选音色，方便 agent 自纠。"""

    code = "UNSUPPORTED_VOICE"

    def __init__(self, voice: str, supported_voices: list[dict]):
        self.voice = voice
        self.supported_voices = supported_voices
        options = ", ".join(f"{v['id']}({v['name']}, {v['gender']})" for v in supported_voices)
        super().__init__(f"不支持的音色 {voice!r}，可选：{options}", {"supported_voices": supported_voices})


class SynthesisError(TTSError):
    """edge-tts 合成失败（网络等）。"""

    code = "SYNTHESIS_FAILED"


class InvalidOutputPathError(TTSError):
    """compose 输出路径不是 WAV 文件。"""

    code = "INVALID_OUTPUT_PATH"

    def __init__(self, output_path: str):
        super().__init__(
            f"compose 输出必须使用 .wav 扩展名，当前路径为 {output_path!r}",
            {"output_path": output_path, "required_extension": ".wav"},
        )


class FFmpegNotFoundError(TTSError):
    """Docker 镜像中没有可用的 FFmpeg。"""

    code = "FFMPEG_NOT_FOUND"

    def __init__(self):
        super().__init__("未找到 FFmpeg，请确认 Docker 镜像已正确安装 ffmpeg")


class AudioProcessingError(TTSError):
    """静音处理、WAV 读取或音频拼接失败。"""

    code = "AUDIO_PROCESSING_FAILED"
