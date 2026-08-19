"""文生图 MCP 输入输出 Schema。"""

TEXT2IMAGE_SAVE_DRAFT_INPUT_SCHEMA = {
    "type": "object",
    "properties": {
        "line": {"type": "string", "minLength": 1, "description": "业务线 id，如 finance"},
        "topic": {"type": "string", "minLength": 1},
        "article": {"type": "string", "minLength": 1},
        "title": {"type": "string", "minLength": 12, "maxLength": 26},
        "short_title": {"type": "string", "minLength": 6, "maxLength": 16},
        "hashtags": {
            "type": "array",
            "minItems": 4,
            "maxItems": 4,
            "uniqueItems": True,
            "items": {"type": "string", "minLength": 1},
        },
        "database_path": {"type": "string"},
        "draft_path": {"type": "string", "description": "修改已生成稿件时传入原 draft_path；话题不得改变"},
    },
    "required": ["line", "topic", "article", "title", "short_title", "hashtags"],
    "additionalProperties": False,
}
