"""视频原语的真实入参和返回合同。

这不是 MCP 注册表。失败时抛出 VideoToolError 子类，不返回 error 对象。
"""

from __future__ import annotations

from ._constants import SUPPORTED_SUBTITLE_LANGUAGES

__all__ = [
    "MOTION_SCHEMA",
    "RENDER_SHOT_INPUT_SCHEMA",
    "RENDER_SHOT_OUTPUT_SCHEMA",
    "COMPOSE_SHOT_ITEM_SCHEMA",
    "COMPOSE_SHOTS_INPUT_SCHEMA",
    "COMPOSE_SHOTS_OUTPUT_SCHEMA",
    "CONCAT_VIDEOS_INPUT_SCHEMA",
    "CONCAT_VIDEOS_OUTPUT_SCHEMA",
    "BURN_SUBTITLES_INPUT_SCHEMA",
    "BURN_SUBTITLES_OUTPUT_SCHEMA",
    "MIX_BGM_INPUT_SCHEMA",
    "MIX_BGM_OUTPUT_SCHEMA",
]

SIZE_SCHEMA = {
    "type": "string",
    "pattern": r"^\s*\d+\s*[xX×]\s*\d+\s*$",
    "description": "输出尺寸，例如 1920x1080",
}

MOTION_SCHEMA = {
    "type": "object",
    "description": "可选确定性缩放/平移动效；不传则为静态画面",
    "properties": {
        "zoom_from": {"type": "number", "minimum": 1.0, "maximum": 2.0},
        "zoom_to": {"type": "number", "minimum": 1.0, "maximum": 2.0},
        "pan_from_x": {"type": "number", "minimum": 0.0, "maximum": 1.0},
        "pan_from_y": {"type": "number", "minimum": 0.0, "maximum": 1.0},
        "pan_to_x": {"type": "number", "minimum": 0.0, "maximum": 1.0},
        "pan_to_y": {"type": "number", "minimum": 0.0, "maximum": 1.0},
    },
    "additionalProperties": False,
}

RENDER_SHOT_INPUT_SCHEMA = {
    "type": "object",
    "description": "render_shot(...) 的关键字参数合同",
    "properties": {
        "image_path": {"type": "string", "minLength": 1},
        "output_path": {"type": "string", "minLength": 1, "description": "单镜头 MP4 路径"},
        "size": SIZE_SCHEMA,
        "duration": {"type": "number", "exclusiveMinimum": 0, "description": "无语音时的镜头时长（秒）"},
        "audio_path": {"type": "string", "description": "语音路径；传入后以语音真实时长为准，忽略 duration"},
        "audio_start": {"type": "number", "minimum": 0},
        "audio_end": {"type": "number", "exclusiveMinimum": 0},
        "subtitle": {"type": "string", "description": "仅记录；单镜头渲染不烧字"},
        "subtitle_language": {"type": "string", "enum": list(SUPPORTED_SUBTITLE_LANGUAGES), "default": "zh"},
        "motion": MOTION_SCHEMA,
    },
    "required": ["image_path", "output_path", "size"],
    "additionalProperties": False,
}

RENDER_SHOT_OUTPUT_SCHEMA = {
    "type": "object",
    "properties": {
        "output_path": {"type": "string"},
        "duration": {"type": "number"},
        "actual_duration": {"type": "number"},
        "duration_source": {"type": "string"},
        "has_audio": {"type": "boolean"},
        "has_subtitle": {"type": "boolean"},
        "has_motion": {"type": "boolean"},
        "audio_start": {"type": ["number", "null"]},
        "audio_end": {"type": ["number", "null"]},
    },
    "required": [
        "output_path", "duration", "actual_duration", "duration_source",
        "has_audio", "has_subtitle", "has_motion", "audio_start", "audio_end",
    ],
    "additionalProperties": False,
}

COMPOSE_SHOT_ITEM_SCHEMA = {
    "type": "object",
    "description": "一个镜头。传入 segment_path 则直接使用该 MP4；否则按图片渲染，且必须有 audio_path 或 duration。",
    "properties": {
        "id": {"type": "string", "minLength": 1},
        "segment_path": {"type": "string"},
        "image_path": {"type": "string"},
        "duration": {"type": "number", "exclusiveMinimum": 0},
        "audio_path": {"type": "string"},
        "audio_start": {"type": "number", "minimum": 0},
        "audio_end": {"type": "number", "exclusiveMinimum": 0},
        "motion": MOTION_SCHEMA,
    },
    "required": ["id"],
    "anyOf": [
        {"required": ["segment_path"]},
        {
            "required": ["image_path"],
            "anyOf": [{"required": ["audio_path"]}, {"required": ["duration"]}],
        },
    ],
    "additionalProperties": False,
}

COMPOSE_SHOTS_INPUT_SCHEMA = {
    "type": "object",
    "description": "compose_shots(...) 的关键字参数合同",
    "properties": {
        "shots": {"type": "array", "minItems": 1, "items": COMPOSE_SHOT_ITEM_SCHEMA},
        "output_path": {"type": "string", "minLength": 1},
        "cache_dir": {"type": "string", "minLength": 1},
        "size": SIZE_SCHEMA,
        "force_shot_ids": {"type": "array", "items": {"type": "string"}, "uniqueItems": True},
    },
    "required": ["shots", "output_path", "cache_dir", "size"],
    "additionalProperties": False,
}

COMPOSE_SHOTS_OUTPUT_SCHEMA = {
    "type": "object",
    "properties": {
        "output_path": {"type": "string"},
        "duration": {"type": "number"},
        "shot_count": {"type": "integer"},
        "cache_hits": {"type": "integer"},
        "rendered_shots": {"type": "integer"},
        "shots": {
            "type": "array",
            "items": {
                "type": "object",
                "properties": {
                    "id": {"type": "string"},
                    "cache_hit": {"type": "boolean"},
                    "pre_rendered": {"type": "boolean"},
                    "segment_path": {"type": "string"},
                    "duration": {"type": "number"},
                },
                "required": ["id", "cache_hit", "pre_rendered", "segment_path", "duration"],
                "additionalProperties": False,
            },
        },
    },
    "required": ["output_path", "duration", "shot_count", "cache_hits", "rendered_shots", "shots"],
    "additionalProperties": False,
}

CONCAT_VIDEOS_INPUT_SCHEMA = {
    "type": "object",
    "description": "concat_videos(...) 的关键字参数合同",
    "properties": {
        "segment_paths": {"type": "array", "minItems": 1, "items": {"type": "string", "minLength": 1}},
        "output_path": {"type": "string", "minLength": 1},
    },
    "required": ["segment_paths", "output_path"],
    "additionalProperties": False,
}

CONCAT_VIDEOS_OUTPUT_SCHEMA = {
    "type": "object",
    "properties": {
        "output_path": {"type": "string"},
        "duration": {"type": "number"},
    },
    "required": ["output_path", "duration"],
    "additionalProperties": False,
}

BURN_SUBTITLES_INPUT_SCHEMA = {
    "type": "object",
    "description": "burn_subtitles(...) 的关键字参数合同",
    "properties": {
        "video_path": {"type": "string", "minLength": 1},
        "cues": {
            "type": "array",
            "minItems": 1,
            "items": {
                "type": "object",
                "properties": {
                    "start": {"type": "number", "minimum": 0},
                    "end": {"type": "number", "exclusiveMinimum": 0},
                    "text": {"type": "string", "minLength": 1},
                    "language": {"type": "string", "enum": list(SUPPORTED_SUBTITLE_LANGUAGES), "default": "zh"},
                },
                "required": ["start", "end", "text"],
                "additionalProperties": False,
            },
        },
        "size": SIZE_SCHEMA,
        "output_path": {"type": "string", "minLength": 1},
    },
    "required": ["video_path", "cues", "size", "output_path"],
    "additionalProperties": False,
}

BURN_SUBTITLES_OUTPUT_SCHEMA = CONCAT_VIDEOS_OUTPUT_SCHEMA

MIX_BGM_INPUT_SCHEMA = {
    "type": "object",
    "description": "mix_bgm(...) 的关键字参数合同",
    "properties": {
        "video_path": {"type": "string", "minLength": 1},
        "bgm_path": {"type": "string", "minLength": 1},
        "output_path": {"type": "string", "minLength": 1},
        "gain": {"type": "number", "minimum": 0},
        "mix_gain": {"type": "number", "minimum": 0},
        "fade_in": {"type": "number", "minimum": 0},
        "fade_out": {"type": "number", "minimum": 0},
    },
    "required": ["video_path", "bgm_path", "output_path"],
    "additionalProperties": False,
}

MIX_BGM_OUTPUT_SCHEMA = {
    "type": "object",
    "properties": {
        "output_path": {"type": "string"},
        "duration": {"type": "number"},
        "bgm_path": {"type": "string"},
        "gain": {"type": "number"},
        "mix_gain": {"type": "number"},
        "fade_in": {"type": "number"},
        "fade_out": {"type": "number"},
    },
    "required": ["output_path", "duration", "bgm_path", "gain", "mix_gain", "fade_in", "fade_out"],
    "additionalProperties": False,
}
