"""generate_shot 的真实入参和返回合同。

这不是 MCP 注册表。失败时抛出 ShotToolError 子类，不返回 error 对象。
"""

from __future__ import annotations

from core.tools.generate_subtitles import SUPPORTED_SUBTITLE_LANGUAGES

__all__ = [
    "MOTION_SCHEMA",
    "GENERATE_SHOT_FROM_IMAGE_INPUT_SCHEMA",
    "GENERATE_SHOT_FROM_IMAGE_OUTPUT_SCHEMA",
    "GENERATE_SHOT_FROM_INTRO_INPUT_SCHEMA",
    "GENERATE_SHOT_FROM_INTRO_OUTPUT_SCHEMA",
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

GENERATE_SHOT_FROM_IMAGE_INPUT_SCHEMA = {
    "type": "object",
    "description": "generate_shot_from_image(...) 的关键字参数合同：只出画面、无音轨，不混合配音",
    "properties": {
        "image_path": {"type": "string", "minLength": 1},
        "output_path": {"type": "string", "minLength": 1, "description": "单镜头 MP4 路径"},
        "size": SIZE_SCHEMA,
        "duration": {"type": "number", "exclusiveMinimum": 0, "description": "镜头时长（秒）"},
        "subtitle": {"type": "string", "description": "仅记录；单镜头渲染不烧字"},
        "subtitle_language": {"type": "string", "enum": list(SUPPORTED_SUBTITLE_LANGUAGES), "default": "zh"},
        "motion": MOTION_SCHEMA,
    },
    "required": ["image_path", "output_path", "size", "duration"],
    "additionalProperties": False,
}

GENERATE_SHOT_FROM_IMAGE_OUTPUT_SCHEMA = {
    "type": "object",
    "properties": {
        "output_path": {"type": "string"},
        "duration": {"type": "number"},
        "actual_duration": {"type": "number"},
        "duration_source": {"type": "string"},
        "has_audio": {"type": "boolean"},
        "has_subtitle": {"type": "boolean"},
        "has_motion": {"type": "boolean"},
    },
    "required": [
        "output_path", "duration", "actual_duration", "duration_source",
        "has_audio", "has_subtitle", "has_motion",
    ],
    "additionalProperties": False,
}

GENERATE_SHOT_FROM_INTRO_INPUT_SCHEMA = {
    "type": "object",
    "description": "generate_shot_from_intro(...) 的关键字参数合同：只出画面；片头音效在成片时叠加",
    "properties": {
        "style": {"type": "string", "enum": ["slide_in_shutter", "page_flip"]},
        "output_path": {"type": "string", "minLength": 1},
        "duration": {"type": "number", "exclusiveMinimum": 0, "description": "第一镜时长（秒），不含配音"},
        "image_path": {"type": "string", "description": "slide_in_shutter 必传"},
        "image_paths": {
            "type": "array",
            "minItems": 9,
            "maxItems": 9,
            "items": {"type": "string"},
            "description": "page_flip 必传的 9 张图；最后一张放大到 duration 结束",
        },
        "sfx_path": {"type": "string", "description": "page_flip 必传的翻页音效"},
        "motion": MOTION_SCHEMA,
    },
    "required": ["style", "output_path", "duration"],
    "additionalProperties": False,
}

GENERATE_SHOT_FROM_INTRO_OUTPUT_SCHEMA = {
    "type": "object",
    "properties": {
        "output_path": {"type": "string"},
        "duration": {"type": "number"},
        "fps": {"type": "integer"},
        "resolution": {"type": "string"},
        "sfx": {"type": "array", "items": {"type": "string"}},
        "has_motion": {"type": "boolean"},
        "page_count": {"type": "integer"},
        "sfx_starts": {"type": "array", "items": {"type": "number"}},
        "opening_sfx": {"type": "array"},
        "last_page_land": {"type": "number"},
    },
    "required": ["output_path", "duration", "fps", "resolution", "sfx"],
    "additionalProperties": False,
}
