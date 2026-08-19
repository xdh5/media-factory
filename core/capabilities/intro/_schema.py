"""slide_in_shutter 的输入输出 JSON Schema。

供 agent 框架注册工具时使用（如 MCP tool 的 inputSchema）。
"""

from __future__ import annotations

from core.tools.video._schema import MOTION_SCHEMA

__all__ = [
    "SLIDE_IN_INPUT_SCHEMA",
    "SLIDE_IN_OUTPUT_SCHEMA",
    "SLIDE_IN_ERROR_SCHEMA",
    "PAGE_FLIP_INPUT_SCHEMA",
    "PAGE_FLIP_OUTPUT_SCHEMA",
]

# 输入参数 schema
SLIDE_IN_INPUT_SCHEMA = {
    "type": "object",
    "properties": {
        "image_path": {
            "type": "string",
            "description": "输入图片路径（建议 16:9 彩色图片；动画内部统一处理为 1920x1080）",
        },
        "output_path": {
            "type": "string",
            "description": "输出 mp4 路径，如 tts_output/intro.mp4（父目录自动创建）",
        },
        "tts_path": {"type": "string", "description": "必传完整 TTS 音频路径"},
        "audio_start": {"type": "number", "minimum": 0, "default": 0},
        "audio_end": {"type": "number", "exclusiveMinimum": 0},
        "subtitle": {"type": "string", "description": "可选。开场动画本身不烧字幕；财经成片由 burn_subtitles 按时间轴一次烧录"},
        "subtitle_language": {"type": "string", "enum": ["zh", "en"], "default": "zh"},
        "motion": MOTION_SCHEMA,
    },
    "required": ["image_path", "tts_path", "output_path"],
    "additionalProperties": False,
}

# 成功输出 schema（slide_in_shutter 的返回值）
SLIDE_IN_OUTPUT_SCHEMA = {
    "type": "object",
    "properties": {
        "output_path": {
            "type": "string",
            "description": "生成的开场动画 mp4 路径",
        },
        "duration": {
            "type": "number",
            "description": "首镜头总时长，以传入 TTS 区间为准",
        },
        "fps": {
            "type": "integer",
            "description": "帧率，固定 30",
        },
        "resolution": {
            "type": "string",
            "description": "分辨率，固定 1920x1080",
        },
        "sfx": {
            "type": "array",
            "items": {"type": "string", "enum": ["whoosh", "shutter"]},
            "description": "实际混入的音效名列表（音效文件缺失时对应项不出现）",
        },
        "audio_start": {"type": "number"},
        "audio_end": {"type": "number"},
        "has_subtitle": {"type": "boolean"},
        "has_motion": {"type": "boolean"},
    },
    "required": [
        "output_path", "duration", "fps", "resolution", "sfx",
        "audio_start", "audio_end", "has_subtitle", "has_motion",
    ],
    "additionalProperties": False,
}

# 错误输出 schema（VideoRenderError.to_dict() 的结构）
SLIDE_IN_ERROR_SCHEMA = {
    "type": "object",
    "properties": {
        "error": {
            "type": "object",
            "properties": {
                "code": {
                    "type": "string",
                    "description": "错误码",
                    "enum": [
                        "INVALID_PARAMETER",  # 参数非法，details.parameter 指出问题参数
                        "FFMPEG_NOT_FOUND",   # 未安装 ffmpeg 或不在 PATH
                        "MEDIA_PROBE_FAILED", # 无法读取 TTS 时长
                        "UNSUPPORTED_SUBTITLE_LANGUAGE", # 字幕语言不支持
                        "RENDER_FAILED",      # ffmpeg 渲染失败，message 带 stderr 摘要
                        "RENDER_TIMEOUT",     # ffmpeg 超时后已终止
                    ],
                },
                "message": {
                    "type": "string",
                    "description": "人类可读错误信息",
                },
                "details": {
                    "type": "object",
                    "description": "附加信息，如 parameter；可为空对象",
                },
            },
            "required": ["code", "message", "details"],
        },
    },
    "required": ["error"],
}

PAGE_FLIP_INPUT_SCHEMA = {
    "type": "object",
    "properties": {
        "image_paths": {
            "type": "array",
            "minItems": 9,
            "maxItems": 9,
            "items": {"type": "string"},
            "description": "翻页用的 9 张图片路径；最后一张会缓慢放大到第一句旁白结束",
        },
        "output_path": {
            "type": "string",
            "description": "输出 mp4 路径（父目录自动创建）",
        },
        "tts_path": {"type": "string", "description": "完整 TTS 音频路径"},
        "sfx_path": {"type": "string", "description": "每次翻页播放的音效路径"},
        "audio_start": {"type": "number", "minimum": 0, "default": 0},
        "audio_end": {"type": "number", "exclusiveMinimum": 0},
    },
    "required": ["image_paths", "tts_path", "sfx_path", "output_path"],
    "additionalProperties": False,
}

PAGE_FLIP_OUTPUT_SCHEMA = {
    "type": "object",
    "properties": {
        "output_path": {"type": "string"},
        "duration": {"type": "number", "description": "首镜头总时长，以传入 TTS 区间为准"},
        "fps": {"type": "integer"},
        "resolution": {"type": "string"},
        "sfx": {"type": "array", "items": {"type": "string"}},
        "audio_start": {"type": "number"},
        "audio_end": {"type": "number"},
        "page_count": {"type": "integer"},
        "flip_starts": {"type": "array", "items": {"type": "number"}},
        "last_page_land": {"type": "number", "description": "最后一页落定并开始放大的时刻"},
    },
    "required": [
        "output_path", "duration", "fps", "resolution", "sfx",
        "audio_start", "audio_end", "page_count", "flip_starts", "last_page_land",
    ],
    "additionalProperties": False,
}
