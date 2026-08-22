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
