"""generate_final_video 的真实入参和返回合同。"""

from __future__ import annotations

__all__ = [
    "GENERATE_FINAL_VIDEO_INPUT_SCHEMA",
    "GENERATE_FINAL_VIDEO_OUTPUT_SCHEMA",
]

GENERATE_FINAL_VIDEO_INPUT_SCHEMA = {
    "type": "object",
    "description": "generate_final_video(...) 的关键字参数合同：拼镜头后合配音；字幕、贴纸、BGM、封面均可选",
    "properties": {
        "shots": {
            "type": "array",
            "minItems": 1,
            "description": "镜头列表。每项有 id，以及 segment_path 或 image_path+duration；可带 subtitle / subtitle_lines / motion",
        },
        "output_path": {"type": "string", "minLength": 1},
        "cache_dir": {"type": "string", "minLength": 1},
        "size": {"type": "string", "description": "输出尺寸，例如 1920x1080"},
        "tts_path": {"type": "string", "minLength": 1},
        "cover_path": {"type": "string", "description": "有封面才传；不传则片身直接当成品"},
        "cover_duration": {"type": "number", "exclusiveMinimum": 0},
        "bgm_path": {"type": "string", "description": "不传则不叠 BGM"},
        "bgm_start_seconds": {
            "type": "number",
            "minimum": 0,
            "description": "BGM 起播时间（秒）；默认 0。财经 slide_in_shutter 由 MCP 按片头拍照结束自动传入",
        },
        "stickers": {"type": "array", "items": {"type": "string"}},
        "opening_sfx": {
            "type": "array",
            "description": "片头音效，在成片时叠加；学语言不传",
            "items": {
                "type": "object",
                "properties": {
                    "path": {"type": "string"},
                    "start": {"type": "number"},
                    "duration": {"type": "number"},
                    "gain": {"type": "number"},
                },
            },
        },
        "force_shot_ids": {"type": "array", "items": {"type": "string"}, "uniqueItems": True},
    },
    "required": [
        "shots", "output_path", "cache_dir", "size", "tts_path",
    ],
    "additionalProperties": False,
}

GENERATE_FINAL_VIDEO_OUTPUT_SCHEMA = {
    "type": "object",
    "properties": {
        "output_path": {"type": "string"},
        "duration": {"type": "number"},
        "body_duration": {"type": "number"},
        "shot_count": {"type": "integer"},
    },
    "required": ["output_path", "duration", "body_duration", "shot_count"],
    "additionalProperties": False,
}
