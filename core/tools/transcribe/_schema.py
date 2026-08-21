"""transcribe 的真实入参和返回合同。"""

from __future__ import annotations

from ._constants import SUPPORTED_LANGUAGES

TRANSCRIBE_INPUT_SCHEMA = {
    "type": "object",
    "description": "把本地音视频转成 Whisper 原文，不做错别字校对",
    "properties": {
        "media_path": {
            "type": "string",
            "minLength": 1,
            "description": "本地音视频路径；远程链接请先调用 core.tools.download.download",
        },
        "language": {
            "type": "string",
            "enum": list(SUPPORTED_LANGUAGES),
            "default": "zh",
            "description": "识别语言；不传为 zh",
        },
        "filename": {"type": "string", "description": "可选展示文件名"},
    },
    "required": ["media_path"],
    "additionalProperties": False,
}

TRANSCRIBE_OUTPUT_SCHEMA = {
    "type": "object",
    "properties": {
        "filename": {"type": "string"},
        "language": {"type": "string"},
        "text": {"type": "string", "description": "Whisper 原文，未经错别字校对"},
        "segments": {
            "type": "array",
            "items": {
                "type": "object",
                "properties": {
                    "start": {"type": ["number", "null"]},
                    "end": {"type": ["number", "null"]},
                    "text": {"type": "string"},
                },
                "required": ["start", "end", "text"],
                "additionalProperties": False,
            },
        },
    },
    "required": ["filename", "language", "text", "segments"],
    "additionalProperties": False,
}
