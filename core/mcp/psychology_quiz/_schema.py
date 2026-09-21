"""心灵鸡汤 MCP 输入结构。"""

QUIZ_SCHEMA = {
    "type": "object",
    "properties": {
        "category": {"type": "string", "enum": ["finance", "success", "human_nature"]},
        "scene_title": {"type": "string", "minLength": 1},
        "scenario": {"type": "string", "minLength": 1},
        "options": {
            "type": "object",
            "properties": {key: {"type": "string", "minLength": 1} for key in ("a", "b", "c", "d")},
            "required": ["a", "b", "c", "d"],
            "additionalProperties": False,
        },
        "results": {
            "type": "object",
            "properties": {key: {"type": "string", "minLength": 1} for key in ("a", "b", "c", "d")},
            "required": ["a", "b", "c", "d"],
            "additionalProperties": False,
        },
        "video_keywords": {
            "type": "array",
            "minItems": 1,
            "maxItems": 20,
            "items": {"type": "string", "minLength": 1},
        },
    },
    "required": ["category", "scene_title", "scenario", "options", "results", "video_keywords"],
    "additionalProperties": False,
}

SAVE_DRAFT_INPUT_SCHEMA = {
    "type": "object",
    "properties": {
        "topic": {"type": "string", "minLength": 1},
        "quiz": QUIZ_SCHEMA,
        "article": {"type": "string", "minLength": 300},
        "title": {"type": "string", "minLength": 12, "maxLength": 26},
        "short_title": {"type": "string", "minLength": 6, "maxLength": 16},
        "hashtags": {"type": "array", "minItems": 4, "maxItems": 4, "items": {"type": "string"}},
        "cover_lines": {"type": "array", "minItems": 1, "maxItems": 3, "items": {"type": "string"}},
        "cover_highlights": {"type": "array", "minItems": 1, "items": {"type": "string"}},
        "publish_date": {"type": "string", "pattern": r"^\d{4}-\d{2}-\d{2}$"},
        "draft_path": {"type": ["string", "null"]},
    },
    "required": [
        "topic", "quiz", "article", "title", "short_title", "hashtags",
        "cover_lines", "cover_highlights", "publish_date",
    ],
    "additionalProperties": False,
}

VIDEO_CONFIG_SCHEMA = {
    "type": "object",
    "properties": {
        "orientation": {"type": "string", "enum": ["landscape", "portrait", "square"]},
        "per_provider": {"type": "integer", "minimum": 1, "maximum": 40},
        "providers": {
            "type": "array",
            "minItems": 1,
            "uniqueItems": True,
            "items": {"type": "string", "enum": ["pexels", "pixabay", "coverr"]},
        },
    },
    "additionalProperties": False,
}
