"""Instagram Graph API 发布 Schema。"""

PUBLISH_TO_INSTAGRAM_INPUT_SCHEMA = {
    "type": "object",
    "properties": {
        "user_id": {"type": "string", "minLength": 1},
        "video_url": {"type": "string", "pattern": r"^https?://"},
        "caption": {"type": "string", "maxLength": 2200},
        "share_to_feed": {"type": "boolean", "default": True},
    },
    "required": ["user_id", "video_url", "caption"],
    "additionalProperties": False,
}

PUBLISH_TO_INSTAGRAM_OUTPUT_SCHEMA = {
    "type": "object",
    "properties": {
        "media_id": {"type": "string"},
        "container_id": {"type": "string"},
        "permalink": {"type": "string"},
        "status": {"type": "string", "const": "published"},
    },
    "required": ["media_id", "container_id", "permalink", "status"],
    "additionalProperties": False,
}

INSTAGRAM_ACCOUNT_SCHEMA = {
    "type": "object",
    "properties": {
        "user_id": {"type": "string"},
        "account_title": {"type": "string"},
        "username": {"type": "string"},
    },
    "required": ["user_id", "account_title", "username"],
    "additionalProperties": False,
}
