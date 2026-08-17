"""YouTube 发布工具输入输出 Schema。"""

from ._constants import YOUTUBE_PRIVACY_STATUSES

PUBLISH_YOUTUBE_VIDEO_INPUT_SCHEMA = {
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
    },
    "required": ["channel_id", "video_path", "title"],
    "additionalProperties": False,
}

YOUTUBE_ACCOUNT_SCHEMA = {
    "type": "object",
    "properties": {
        "channel_id": {"type": "string"},
        "channel_title": {"type": "string"},
        "thumbnail_url": {"type": "string"},
    },
    "required": ["channel_id", "channel_title", "thumbnail_url"],
    "additionalProperties": False,
}

PUBLISH_YOUTUBE_VIDEO_OUTPUT_SCHEMA = {
    "type": "object",
    "properties": {
        "video_id": {"type": "string"},
        "video_url": {"type": "string"},
        "channel_id": {"type": "string"},
    },
    "required": ["video_id", "video_url", "channel_id"],
    "additionalProperties": False,
}

MIGRATE_YOUTUBE_ACCOUNTS_INPUT_SCHEMA = {
    "type": "object",
    "properties": {
        "source_token_dir": {"type": "string", "minLength": 1},
        "channel_ids": {
            "type": "array",
            "items": {"type": "string", "minLength": 1},
            "uniqueItems": True,
        },
    },
    "required": ["source_token_dir"],
    "additionalProperties": False,
}

MIGRATE_YOUTUBE_ACCOUNTS_OUTPUT_SCHEMA = {
    "type": "object",
    "properties": {
        "source_token_dir": {"type": "string"},
        "target_token_dir": {"type": "string"},
        "copied": {"type": "integer"},
        "accounts": {"type": "array", "items": YOUTUBE_ACCOUNT_SCHEMA},
    },
    "required": ["source_token_dir", "target_token_dir", "copied", "accounts"],
    "additionalProperties": False,
}
