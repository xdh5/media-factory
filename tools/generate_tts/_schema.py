"""generate_tts 的真实入参和返回合同。

这不是 MCP 注册表。失败时抛出 TTSError 子类，不返回 error 对象。
"""

from __future__ import annotations

__all__ = [
    "GENERATE_TTS_INPUT_SCHEMA",
    "GENERATE_TTS_OUTPUT_SCHEMA",
]

TTS_LINE_SCHEMA = {
    "type": "object",
    "description": "一句台词及其音色",
    "properties": {
        "text": {"type": "string", "minLength": 1, "description": "该段台词"},
        "voice": {
            "type": "string",
            "minLength": 1,
            "description": "该段音色 id 或 name，如 zh-CN-YunjianNeural 或 Yunjian",
        },
        "rate": {
            "type": "string",
            "description": "该段 Edge TTS 倍速，如 +20%；不传则用 generate_tts 的 rate 参数",
        },
    },
    "required": ["text", "voice"],
    "additionalProperties": False,
}

GENERATE_TTS_INPUT_SCHEMA = {
    "type": "object",
    "description": "generate_tts(...) 的关键字参数合同",
    "properties": {
        "script": {
            "type": "array",
            "minItems": 1,
            "description": "台词数组；每一项自带音色。单句传长度为 1 的数组",
            "items": TTS_LINE_SCHEMA,
        },
        "output_path": {
            "type": "string",
            "description": "输出路径；返回路径按服务原格式使用 WAV 或 MP3",
        },
        "rate": {
            "type": "string",
            "default": "+0%",
            "description": "Edge TTS 倍速，如 +0%、+20%、-10%；不传为原速 +0%。单句可用 script[].rate 覆盖",
        },
    },
    "required": ["script", "output_path"],
    "additionalProperties": False,
}

GENERATE_TTS_OUTPUT_SCHEMA = {
    "type": "object",
    "description": "generate_tts 成功时返回的 dict",
    "properties": {
        "line_count": {"type": "integer", "description": "非空台词行数"},
        "total_duration": {"type": "number", "description": "原始配音拼接时长（秒）"},
        "timeline": {
            "type": "array",
            "description": "每行台词时间轴，按原始音频时长和输入顺序累计",
            "items": {
                "type": "object",
                "properties": {
                    "id": {"type": "string"},
                    "text": {"type": "string"},
                    "voice": {"type": "string"},
                    "rate": {"type": "string"},
                    "start": {"type": "number"},
                    "end": {"type": "number"},
                    "duration": {"type": "number"},
                },
                "required": ["id", "text", "voice", "rate", "start", "end", "duration"],
                "additionalProperties": False,
            },
        },
        "output_path": {"type": "string"},
    },
    "required": [
        "line_count", "total_duration", "timeline", "output_path",
        "rate",
    ],
    "additionalProperties": False,
}
