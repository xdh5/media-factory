"""Cloudflare 数据服务输入输出 Schema。"""

TOPIC_RECORD_SCHEMA = {
    "type": "object",
    "properties": {
        "id": {"type": "integer"},
        "workflow": {"type": "string"},
        "topic": {"type": "string"},
        "fingerprint": {"type": "string"},
        "status": {"type": "string"},
        "created_at": {"type": "string"},
        "updated_at": {"type": "string"},
        "publication_id": {"type": ["string", "null"]},
    },
    "required": ["id", "workflow", "topic", "fingerprint", "status", "created_at", "updated_at"],
    "additionalProperties": False,
}

PUBLICATION_COMMIT_SCHEMA = {
    "type": "object",
    "properties": {
        "record": TOPIC_RECORD_SCHEMA,
        "already_committed": {"type": "boolean"},
        "word_count": {"type": "integer", "minimum": 0},
    },
    "required": ["record", "already_committed", "word_count"],
    "additionalProperties": False,
}

IMAGE_RECORD_SCHEMA = {
    "type": "object",
    "properties": {
        "id": {"type": "integer"},
        "caption": {"type": "string"},
        "image_path": {"type": ["string", "null"]},
    },
    "required": ["id", "caption", "image_path"],
    "additionalProperties": False,
}

PUBLISH_ACCOUNT_SCHEMA = {
    "type": "object",
    "properties": {
        "code": {"type": "string"},
        "platform": {"type": "string"},
        "display_name": {"type": "string"},
        "connector": {"type": "string"},
        "config_key": {"type": "string"},
        "config": {"type": "object"},
        "position": {"type": "integer", "minimum": 0},
        "enabled": {"type": "boolean"},
    },
    "required": [
        "code",
        "platform",
        "display_name",
        "connector",
        "config_key",
        "config",
        "position",
        "enabled",
    ],
    "additionalProperties": False,
}

PUBLISH_ACCOUNT_GROUP_SCHEMA = {
    "type": "object",
    "properties": {
        "code": {"type": "string"},
        "name": {"type": "string"},
        "workflow": {"type": "string"},
        "enabled": {"type": "boolean"},
        "members": {"type": "array", "items": PUBLISH_ACCOUNT_SCHEMA},
    },
    "required": ["code", "name", "workflow", "enabled", "members"],
    "additionalProperties": False,
}

CLOUDFLARE_DATA_ERROR_SCHEMA = {
    "type": "object",
    "properties": {
        "error": {
            "type": "object",
            "properties": {
                "code": {
                    "type": "string",
                    "enum": [
                        "CLOUDFLARE_DATA_ERROR",
                        "CLOUDFLARE_DATA_CONFIGURATION_ERROR",
                        "CLOUDFLARE_DATA_REQUEST_ERROR",
                        "CLOUDFLARE_DATA_CONFLICT",
                    ],
                },
                "message": {"type": "string"},
                "details": {"type": "object"},
            },
            "required": ["code", "message", "details"],
        }
    },
    "required": ["error"],
}

DOUYIN_RESEARCH_RECORD_SCHEMA = {
    "type": "object",
    "properties": {
        "aweme_id": {"type": "string"},
        "source_keyword": {"type": "string"},
        "search_rank": {"type": "integer", "minimum": 1},
        "author_name": {"type": "string"},
        "published_at": {"type": ["string", "null"]},
        "caption": {"type": "string"},
        "transcript_raw": {"type": "string"},
        "transcript_corrected": {"type": "string"},
        "aweme_url": {"type": "string"},
        "cover_url": {"type": ["string", "null"]},
        "created_at": {"type": "string"},
        "updated_at": {"type": "string"},
    },
    "required": [
        "aweme_id", "source_keyword", "search_rank", "author_name", "caption",
        "transcript_raw", "transcript_corrected", "aweme_url", "created_at", "updated_at",
    ],
    "additionalProperties": False,
}
