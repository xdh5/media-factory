"""心灵鸡汤 MCP 输入结构。"""

SAVE_DRAFT_INPUT_SCHEMA = {
    "type": "object",
    "properties": {
        "topic": {"type": "string", "minLength": 1},
        "article": {"type": "string", "minLength": 300},
        "intro_scene": {
            "type": "string",
            "minLength": 1,
            "description": "片头写实图场景描述：人物身份 + 关键动作 + 环境细节，从文章提炼",
        },
        "title": {"type": "string", "minLength": 12, "maxLength": 26},
        "short_title": {"type": "string", "minLength": 6, "maxLength": 16},
        "hashtags": {"type": "array", "minItems": 4, "maxItems": 4, "items": {"type": "string"}},
        "cover_lines": {"type": "array", "minItems": 1, "maxItems": 3, "items": {"type": "string"}},
        "cover_highlights": {"type": "array", "minItems": 1, "items": {"type": "string"}},
        "publish_date": {"type": "string", "pattern": r"^\d{4}-\d{2}-\d{2}$"},
        "draft_path": {"type": ["string", "null"]},
    },
    "required": [
        "topic", "article", "intro_scene", "title", "short_title", "hashtags",
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
