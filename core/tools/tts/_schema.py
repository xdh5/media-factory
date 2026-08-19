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
            "description": "输出 WAV 路径（24 kHz、单声道、PCM）",
        },
        "pause_start": {
            "type": "number",
            "minimum": 0,
            "default": 0,
            "description": "整条配音开头静音秒数；不传为 0",
        },
        "pause_between": {
            "type": "number",
            "minimum": 0,
            "description": "相邻两句之间保留在上一句句尾的静音秒数；不传用工具默认句间隔",
        },
        "pause_end": {
            "type": "number",
            "minimum": 0,
            "description": "最后一句句尾静音秒数；不传用工具默认片尾静音",
        },
        "rate": {
            "type": "string",
            "default": "+0%",
            "description": "Edge TTS 倍速，如 +0%、+20%、-10%；不传为原速 +0%。单句可用 script[].rate 覆盖",
        },
        "trim_trailing_silence": {
            "type": "boolean",
            "default": False,
            "description": "为 true 时裁掉句尾低于阈值的静音并保留 pause_between/pause_end；为 false 时保留完整读音，再另垫静音。不传为 false",
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
        "total_duration": {"type": "number", "description": "最终 WAV 时长（秒，含片头/句间/片尾静音）"},
        "timeline": {
            "type": "array",
            "description": "每行台词时间轴，按输入顺序；时长含该行规定静音",
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
        "pause_start": {"type": "number"},
        "pause_between": {"type": "number"},
        "pause_end": {"type": "number"},
        "rate": {"type": "string"},
        "trim_trailing_silence": {"type": "boolean"},
        "loudness": {
            "type": "object",
            "description": "内部响度标准化结果；时长与时间轴采样帧数一致",
            "properties": {
                "output_path": {"type": "string"},
                "target_lufs": {"type": "number"},
                "true_peak_db": {"type": "number"},
                "lra": {"type": "number"},
                "sample_rate": {"type": "integer"},
                "channels": {"type": "integer"},
                "frames": {"type": "integer"},
                "duration": {"type": "number"},
                "cache_hit": {"type": "boolean"},
            },
            "required": [
                "output_path", "target_lufs", "true_peak_db", "lra", "sample_rate",
                "channels", "frames", "duration", "cache_hit",
            ],
            "additionalProperties": False,
        },
    },
    "required": [
        "line_count", "total_duration", "timeline", "output_path",
        "pause_start", "pause_between", "pause_end", "rate", "trim_trailing_silence", "loudness",
    ],
    "additionalProperties": False,
}
