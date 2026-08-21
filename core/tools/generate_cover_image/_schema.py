"""生成封面图片 JSON Schema。"""

from __future__ import annotations

from ._constants import DEFAULT_COVER_SIZE

GENERATE_COVER_IMAGE_INPUT_SCHEMA = {
    "type": "object",
    "properties": {
        "images": {
            "type": "array",
            "minItems": 1,
            "items": {"type": "string", "minLength": 1},
            "description": "候选底图路径；工具会随机抽一张刻标题",
        },
        "title": {"type": "string", "minLength": 1},
        "output_path": {"type": "string", "minLength": 1},
        "size": {"type": "string", "default": DEFAULT_COVER_SIZE},
        "font_path": {"type": "string"},
        "seed": {"type": "integer"},
        "lines": {
            "type": "array",
            "minItems": 1,
            "items": {"type": "string", "minLength": 1},
            "description": "Agent 为长标题按语义断好的行；拼接后必须等于 title。工具不自动折行，只按行缩放字号",
        },
    },
    "required": ["images", "title", "output_path"],
    "additionalProperties": False,
}

GENERATE_COVER_IMAGE_OUTPUT_SCHEMA = {
    "type": "object",
    "properties": {
        "output_path": {"type": "string"},
        "source_image_path": {"type": "string"},
        "title": {"type": "string"},
        "size": {"type": "string"},
        "font_path": {"type": "string"},
        "fill_color": {"type": "array", "items": {"type": "integer"}, "minItems": 3, "maxItems": 3},
        "stroke_color": {"type": "array", "items": {"type": "integer"}, "minItems": 3, "maxItems": 3},
        "theme_color": {"type": "array", "items": {"type": "integer"}, "minItems": 3, "maxItems": 3},
        "lines": {"type": "array", "items": {"type": "string"}},
    },
    "required": [
        "output_path", "source_image_path", "title", "size", "font_path",
        "fill_color", "stroke_color", "theme_color", "lines",
    ],
    "additionalProperties": False,
}
