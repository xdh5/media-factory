"""视频合成工具的输入输出 JSON Schema。"""

from __future__ import annotations

from ._constants import SUPPORTED_SUBTITLE_LANGUAGES

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

SELECT_SUBTITLE_INPUT_SCHEMA = {
    "type": "object",
    "properties": {
        "language": {"type": "string", "enum": SUPPORTED_SUBTITLE_LANGUAGES},
        "size": {"type": "string", "pattern": r"^\s*\d+\s*[xX×]\s*\d+\s*$", "description": "目标画布尺寸，例如 1920x1080"},
    },
    "required": ["language", "size"],
    "additionalProperties": False,
}

SELECT_SUBTITLE_OUTPUT_SCHEMA = {
    "type": "object",
    "properties": {
        "language": {"type": "string"},
        "font": {"type": "string"},
        "canvas_width": {"type": "integer"},
        "canvas_height": {"type": "integer"},
        "font_size": {"type": "integer"},
        "alignment": {"type": "integer"},
        "margin_left": {"type": "integer"},
        "margin_right": {"type": "integer"},
        "margin_vertical": {"type": "integer"},
        "max_width": {"type": "integer"},
        "outline": {"type": "integer"},
        "shadow": {"type": "integer"},
    },
    "required": [
        "language", "font", "canvas_width", "canvas_height", "font_size", "alignment", "margin_left",
        "margin_right", "margin_vertical", "max_width", "outline", "shadow",
    ],
}

SHOT_PROPERTIES = {
    "image_path": {"type": "string", "description": "静态图片路径"},
    "duration": {"type": "number", "exclusiveMinimum": 0, "description": "无语音时的镜头时长"},
    "audio_path": {"type": "string", "description": "可选语音路径；存在时忽略 duration"},
    "audio_start": {"type": "number", "minimum": 0, "description": "从完整语音中截取的起点秒数"},
    "audio_end": {"type": "number", "exclusiveMinimum": 0, "description": "从完整语音中截取的终点秒数"},
    "subtitle": {"type": "string", "description": "可选字幕文本；不传则无字幕"},
    "subtitle_language": {"type": "string", "enum": SUPPORTED_SUBTITLE_LANGUAGES, "default": "zh"},
    "motion": MOTION_SCHEMA,
}

RENDER_SHOT_INPUT_SCHEMA = {
    "type": "object",
    "properties": {
        **SHOT_PROPERTIES,
        "size": {"type": "string", "pattern": r"^\s*\d+\s*[xX×]\s*\d+\s*$"},
        "output_path": {"type": "string", "description": "单镜头 MP4 输出路径"},
    },
    "required": ["image_path", "output_path", "size"],
    "anyOf": [{"required": ["audio_path"]}, {"required": ["duration"]}],
    "additionalProperties": False,
}

RENDER_SHOT_OUTPUT_SCHEMA = {
    "type": "object",
    "properties": {
        "output_path": {"type": "string"},
        "duration": {"type": "number"},
        "actual_duration": {"type": "number"},
        "duration_source": {"type": "string", "enum": ["audio", "duration"]},
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
}

COMPOSE_VIDEO_INPUT_SCHEMA = {
    "type": "object",
    "properties": {
        "shots": {
            "type": "array",
            "minItems": 1,
            "items": {
                "type": "object",
                "properties": {"id": {"type": "string", "minLength": 1}, **SHOT_PROPERTIES},
                "required": ["id", "image_path"],
                "anyOf": [{"required": ["audio_path"]}, {"required": ["duration"]}],
                "additionalProperties": False,
            },
        },
        "output_path": {"type": "string"},
        "size": {"type": "string", "pattern": r"^\s*\d+\s*[xX×]\s*\d+\s*$", "description": "全部镜头统一输出尺寸"},
        "cache_dir": {"type": "string"},
        "force_shot_ids": {"type": "array", "items": {"type": "string"}, "uniqueItems": True},
    },
    "required": ["shots", "output_path", "cache_dir", "size"],
    "additionalProperties": False,
}

COMPOSE_VIDEO_OUTPUT_SCHEMA = {
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
                    "segment_path": {"type": "string"},
                    "duration": {"type": "number"},
                },
                "required": ["id", "cache_hit", "segment_path", "duration"],
            },
        },
    },
    "required": ["output_path", "duration", "shot_count", "cache_hits", "rendered_shots", "shots"],
}

CONCAT_SEGMENTS_INPUT_SCHEMA = {
    "type": "object",
    "properties": {
        "segment_paths": {"type": "array", "minItems": 1, "items": {"type": "string"}},
        "output_path": {"type": "string"},
    },
    "required": ["segment_paths", "output_path"],
    "additionalProperties": False,
}

CONCAT_SEGMENTS_OUTPUT_SCHEMA = {
    "type": "object",
    "properties": {
        "output_path": {"type": "string"},
        "duration": {"type": "number"},
        "segment_count": {"type": "integer"},
    },
    "required": ["output_path", "duration", "segment_count"],
    "additionalProperties": False,
}

PREPEND_COVER_FRAME_INPUT_SCHEMA = {
    "type": "object",
    "properties": {
        "cover_path": {"type": "string"},
        "video_path": {"type": "string"},
        "output_path": {"type": "string"},
        "size": {"type": "string", "pattern": r"^\s*\d+\s*[xX×]\s*\d+\s*$"},
    },
    "required": ["cover_path", "video_path", "output_path", "size"],
    "additionalProperties": False,
}

PREPEND_COVER_FRAME_OUTPUT_SCHEMA = {
    "type": "object",
    "properties": {
        "output_path": {"type": "string"},
        "duration": {"type": "number"},
        "cover_frames": {"type": "integer", "const": 1},
        "fps": {"type": "integer"},
    },
    "required": ["output_path", "duration", "cover_frames", "fps"],
    "additionalProperties": False,
}

MIX_BGM_INPUT_SCHEMA = {
    "type": "object",
    "properties": {
        "video_path": {"type": "string"},
        "bgm_path": {"type": "string"},
        "output_path": {"type": "string"},
        "gain": {"type": "number", "minimum": 0},
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
        "fade_in": {"type": "number"},
        "fade_out": {"type": "number"},
    },
    "required": ["output_path", "duration", "bgm_path", "gain", "fade_in", "fade_out"],
    "additionalProperties": False,
}

VIDEO_ERROR_SCHEMA = {
    "type": "object",
    "properties": {
        "error": {
            "type": "object",
            "properties": {
                "code": {
                    "type": "string",
                    "enum": [
                        "INVALID_PARAMETER", "UNSUPPORTED_SUBTITLE_LANGUAGE",
                        "MEDIA_FILE_NOT_FOUND", "FFMPEG_NOT_FOUND", "MEDIA_PROBE_FAILED",
                        "RENDER_FAILED", "CACHE_FAILED",
                    ],
                },
                "message": {"type": "string"},
                "details": {"type": "object"},
            },
            "required": ["code", "message", "details"],
        },
    },
    "required": ["error"],
}
