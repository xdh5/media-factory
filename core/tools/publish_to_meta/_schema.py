"""发布到 Facebook / Instagram Reels 的输入输出 Schema。"""

from ._constants import META_PLATFORMS

PUBLISH_TO_META_INPUT_SCHEMA = {
    "type": "object",
    "properties": {
        "video_path": {"type": "string", "minLength": 1},
        "video_url": {"type": "string", "minLength": 8},
        "title": {"type": "string", "minLength": 1, "maxLength": 2200},
        "account": {"type": "string", "minLength": 1, "description": "账号标识，对应 .env 前缀，如 language_learning"},
        "description": {"type": "string"},
        "platforms": {
            "type": "array",
            "minItems": 1,
            "items": {"type": "string", "enum": list(META_PLATFORMS)},
        },
    },
    "required": ["title"],
    "additionalProperties": False,
}

META_ACCOUNT_SCHEMA = {
    "type": "object",
    "properties": {
        "account": {"type": "string"},
        "platform": {"type": "string", "enum": list(META_PLATFORMS)},
        "account_id": {"type": "string"},
        "ready": {"type": "boolean"},
    },
    "required": ["account", "platform", "account_id", "ready"],
    "additionalProperties": False,
}

PUBLISH_TO_META_OUTPUT_SCHEMA = {
    "type": "object",
    "properties": {
        "title": {"type": "string"},
        "account": {"type": "string"},
        "platforms": {
            "type": "array",
            "items": {
                "type": "object",
                "properties": {
                    "platform": {"type": "string"},
                    "success": {"type": "boolean"},
                    "media_id": {"type": "string"},
                    "permalink": {"type": "string"},
                },
                "required": ["platform", "success"],
                "additionalProperties": True,
            },
        },
    },
    "required": ["title", "platforms"],
    "additionalProperties": False,
}

UPLOAD_PUBLIC_FILE_INPUT_SCHEMA = {
    "type": "object",
    "properties": {
        "file_path": {"type": "string", "minLength": 1},
        "object_key": {"type": "string", "minLength": 1, "maxLength": 512},
        "content_type": {"type": "string", "minLength": 1},
    },
    "required": ["file_path", "object_key"],
    "additionalProperties": False,
}

UPLOAD_PUBLIC_FILE_OUTPUT_SCHEMA = {
    "type": "object",
    "properties": {
        "url": {"type": "string", "minLength": 1},
        "key": {"type": "string"},
        "bucket": {"type": "string"},
        "size": {"type": "integer"},
    },
    "required": ["url", "key", "bucket", "size"],
    "additionalProperties": False,
}
