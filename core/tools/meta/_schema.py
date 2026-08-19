"""Facebook / Instagram Reels 发布输入输出 Schema。"""

from ._constants import META_PLATFORMS

PUBLISH_META_REEL_INPUT_SCHEMA = {
    "type": "object",
    "properties": {
        "video_path": {"type": "string", "minLength": 1},
        "video_url": {"type": "string", "minLength": 8},
        "title": {"type": "string", "minLength": 1, "maxLength": 2200},
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
        "platform": {"type": "string", "enum": list(META_PLATFORMS)},
        "account_id": {"type": "string"},
        "ready": {"type": "boolean"},
    },
    "required": ["platform", "account_id", "ready"],
    "additionalProperties": False,
}

PUBLISH_META_REEL_OUTPUT_SCHEMA = {
    "type": "object",
    "properties": {
        "title": {"type": "string"},
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
