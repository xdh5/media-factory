"""transcribe 的真实入参和返回合同。"""

from __future__ import annotations

from ._constants import SUPPORTED_LANGUAGES

TRANSCRIBE_INPUT_SCHEMA = {
    "type": "object",
    "description": "把本地音视频转成文字。中文会再调用一次模型补标点并改错别字",
    "properties": {
        "media_path": {
            "type": "string",
            "minLength": 1,
            "description": "本地音视频路径；远程链接请先调用 download_video.download",
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
        "text": {"type": "string", "description": "中文为补标点并改错别字后的正文，其他语言为识别原文"},
        "raw_text": {"type": "string", "description": "语音识别原文"},
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
    "required": ["filename", "language", "text", "raw_text", "segments"],
    "additionalProperties": False,
}
