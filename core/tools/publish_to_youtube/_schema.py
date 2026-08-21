"""发布到 YouTube 的输入输出 Schema。"""

from ._constants import YOUTUBE_PRIVACY_STATUSES

PUBLISH_TO_YOUTUBE_INPUT_SCHEMA = {
    "type": "object",
    "properties": {
        "channel_id": {"type": "string", "minLength": 1},
        "video_path": {"type": "string", "minLength": 1},
        "title": {"type": "string", "minLength": 1, "maxLength": 100},
        "description": {"type": "string"},
        "tags": {"type": "array", "items": {"type": "string", "minLength": 1}},
        "category_id": {"type": "string", "minLength": 1, "default": "24"},
        "privacy_status": {"type": "string", "enum": YOUTUBE_PRIVACY_STATUSES, "default": "private"},
        "thumbnail_path": {"type": "string"},
        "caption_path": {"type": "string"},
        "language": {"type": "string", "minLength": 2, "default": "zh"},
        "account": {"type": "string", "minLength": 1, "description": "账号标识，对应 .env 前缀，如 language_learning"},
    },
    "required": ["channel_id", "video_path", "title"],
    "additionalProperties": False,
}

YOUTUBE_ACCOUNT_SCHEMA = {
    "type": "object",
    "properties": {
        "account": {"type": "string"},
        "channel_id": {"type": "string"},
        "channel_title": {"type": "string"},
        "thumbnail_url": {"type": "string"},
    },
    "required": ["account", "channel_id", "channel_title", "thumbnail_url"],
    "additionalProperties": False,
}

PUBLISH_TO_YOUTUBE_OUTPUT_SCHEMA = {
    "type": "object",
    "properties": {
        "video_id": {"type": "string"},
        "video_url": {"type": "string"},
        "channel_id": {"type": "string"},
    },
    "required": ["video_id", "video_url", "channel_id"],
    "additionalProperties": False,
}
