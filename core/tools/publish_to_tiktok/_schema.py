"""Zernio TikTok 发布输入输出 Schema。"""

PUBLISH_TO_TIKTOK_INPUT_SCHEMA = {
    "type": "object",
    "properties": {
        "account_id": {"type": "string", "minLength": 1},
        "video_url": {"type": "string", "format": "uri"},
        "content": {"type": "string", "maxLength": 2200},
        "account": {
            "type": "string",
            "minLength": 1,
            "description": "账号标识，对应环境变量前缀，例如 language_learning",
        },
    },
    "required": ["account_id", "video_url", "content"],
    "additionalProperties": False,
}

TIKTOK_ACCOUNT_SCHEMA = {
    "type": "object",
    "properties": {
        "account": {"type": "string"},
        "account_id": {"type": "string"},
        "account_title": {"type": "string"},
        "username": {"type": "string"},
    },
    "required": ["account", "account_id", "account_title", "username"],
    "additionalProperties": False,
}

PUBLISH_TO_TIKTOK_OUTPUT_SCHEMA = {
    "type": "object",
    "properties": {
        "post_id": {"type": "string"},
        "platform_url": {"type": "string"},
        "account_id": {"type": "string"},
        "duplicate": {"type": "boolean"},
    },
    "required": ["post_id", "platform_url", "account_id", "duplicate"],
    "additionalProperties": False,
}
