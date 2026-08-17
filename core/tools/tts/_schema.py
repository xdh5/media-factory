"""TTS 工具的输入输出 JSON Schema。

供 agent 框架注册工具时使用（如 MCP tool 的 inputSchema），
也可直接暴露给 agent 查询合法取值。
"""

from __future__ import annotations

__all__ = [
    "SYNTHESIZE_INPUT_SCHEMA",
    "SYNTHESIZE_OUTPUT_SCHEMA",
    "SYNTHESIZE_ERROR_SCHEMA",
    "COMPOSE_INPUT_SCHEMA",
    "COMPOSE_OUTPUT_SCHEMA",
    "COMPOSE_ERROR_SCHEMA",
]

# 输入参数 schema
SYNTHESIZE_INPUT_SCHEMA = {
    "type": "object",
    "properties": {
        "text": {
            "type": "string",
            "description": "待合成文本，去掉首尾空白后不能为空",
        },
        "output_path": {
            "type": "string",
            "description": "输出 mp3 文件路径，如 tts_output/a.mp3",
        },
        "voice": {
            "type": "string",
            "description": "音色 id 或 name，如 'zh-CN-XiaoxiaoNeural' 或 'Xiaoxiao'，语言由音色决定",
        },
    },
    "required": ["text", "output_path", "voice"],
}

# 成功输出 schema
SYNTHESIZE_OUTPUT_SCHEMA = {
    "type": "object",
    "properties": {
        "text": {
            "type": "string",
            "description": "原文本",
        },
        "audio_path": {
            "type": "string",
            "description": "音频文件路径",
        },
        "duration": {
            "type": "number",
            "description": "语音时长（秒，不含尾部静音）",
        },
    },
    "required": ["text", "audio_path", "duration"],
}

# 错误输出 schema（TTSError.to_dict() 的结构）
SYNTHESIZE_ERROR_SCHEMA = {
    "type": "object",
    "properties": {
        "error": {
            "type": "object",
            "properties": {
                "code": {
                    "type": "string",
                    "description": "错误码",
                    "enum": [
                        "EMPTY_TEXT",           # 待合成文本为空
                        "UNSUPPORTED_VOICE",    # 音色不在音色库，details 里有 supported_voices
                        "SYNTHESIS_FAILED",     # 合成失败（网络等）
                    ],
                },
                "message": {
                    "type": "string",
                    "description": "人类可读错误信息",
                },
                "details": {
                    "type": "object",
                    "description": "附加信息，如 supported_voices；可为空对象",
                },
            },
            "required": ["code", "message", "details"],
        },
    },
    "required": ["error"],
}

# compose 输入 schema
COMPOSE_INPUT_SCHEMA = {
    "type": "object",
    "properties": {
        "script": {
            "type": "string",
            "description": "多行台词文本，每个非空行合成一段，全部行共用同一音色",
        },
        "output_path": {
            "type": "string",
            "description": "输出 WAV 文件路径（24 kHz、单声道、PCM），如 tts_output/narration.wav",
        },
        "voice": {
            "type": "string",
            "description": "音色 id 或 name，如 'zh-CN-YunjianNeural' 或 'Yunjian'，语言由音色决定",
        },
    },
    "required": ["script", "output_path", "voice"],
}

# compose 成功输出 schema
COMPOSE_OUTPUT_SCHEMA = {
    "type": "object",
    "properties": {
        "line_count": {
            "type": "integer",
            "description": "台词行数（非空行）",
        },
        "total_duration": {
            "type": "number",
            "description": "最终 WAV 的真实采样时长（秒，包含句间和末尾静音）",
        },
        "timeline": {
            "type": "array",
            "description": "每行台词的时间轴，按输入顺序",
            "items": {
                "type": "object",
                "properties": {
                    "id": {
                        "type": "string",
                        "description": "行标识，如 L001",
                    },
                    "text": {
                        "type": "string",
                        "description": "该行台词原文",
                    },
                    "start": {
                        "type": "number",
                        "description": "起始时间（秒）",
                    },
                    "end": {
                        "type": "number",
                        "description": "结束时间（秒）",
                    },
                    "duration": {
                        "type": "number",
                        "description": "该段处理后 WAV 的真实采样时长（秒，包含规定静音）",
                    },
                },
                "required": ["id", "text", "start", "end", "duration"],
            },
        },
        "output_path": {
            "type": "string",
            "description": "拼接后的音频文件路径",
        },
    },
    "required": ["line_count", "total_duration", "timeline", "output_path"],
}

# compose 错误输出 schema（结构与 SYNTHESIZE_ERROR_SCHEMA 相同，错误码含义针对 compose 场景）
COMPOSE_ERROR_SCHEMA = {
    "type": "object",
    "properties": {
        "error": {
            "type": "object",
            "properties": {
                "code": {
                    "type": "string",
                    "description": "错误码",
                    "enum": [
                        "EMPTY_TEXT",           # 台词没有非空行
                        "UNSUPPORTED_VOICE",    # 音色不在音色库，details 里有 supported_voices
                        "SYNTHESIS_FAILED",     # 任一行合成失败（网络等）
                        "INVALID_OUTPUT_PATH", # 输出不是 .wav
                        "FFMPEG_NOT_FOUND",    # Docker 镜像中没有 ffmpeg
                        "AUDIO_PROCESSING_FAILED", # 静音处理、WAV 读取或拼接失败
                    ],
                },
                "message": {
                    "type": "string",
                    "description": "人类可读错误信息",
                },
                "details": {
                    "type": "object",
                    "description": "附加信息，如 supported_voices；可为空对象",
                },
            },
            "required": ["code", "message", "details"],
        },
    },
    "required": ["error"],
}
