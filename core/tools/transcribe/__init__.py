"""语音转文字公开入口。"""

from ._errors import TranscriptionError
from .transcribe import transcribe

__all__ = [
    "transcribe",
    "TranscriptionError",
]
