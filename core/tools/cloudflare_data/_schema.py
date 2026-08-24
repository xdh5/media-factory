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

FINANCE_GENERATED_IMAGE_COMMIT_INPUT_SCHEMA = {
    "type": "object",
    "properties": {
        "records": {
            "type": "array",
            "minItems": 1,
            "maxItems": 100,
            "items": {
                "type": "object",
                "properties": {
                    "caption": {"type": "string", "minLength": 1, "maxLength": 4000},
                    "image_path": {
                        "type": "string",
                        "minLength": 1,
                        "maxLength": 1000,
                        "pattern": r"^data/image_library_finance/[1-9]\d*\.png$",
                    },
                },
                "required": ["caption", "image_path"],
                "additionalProperties": False,
            },
        },
    },
    "required": ["records"],
    "additionalProperties": False,
}

FINANCE_GENERATED_IMAGE_OUTPUT_SCHEMA = {
    "type": "object",
    "properties": {
        "records": {"type": "array", "items": IMAGE_RECORD_SCHEMA},
    },
    "required": ["records"],
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
        "aweme_id", "author_name", "caption",
        "transcript_raw", "transcript_corrected", "aweme_url", "created_at", "updated_at",
    ],
    "additionalProperties": False,
}

DOUYIN_RESEARCH_SCRIPT_SOURCE_SCHEMA = {
    "type": "object",
    "properties": {
        "aweme_id": {"type": "string"},
        "caption": {"type": "string"},
        "transcript": {"type": "string"},
        "aweme_url": {"type": "string"},
        "collection_code": {"type": "string"},
    },
    "required": ["aweme_id", "caption", "transcript", "aweme_url", "collection_code"],
    "additionalProperties": False,
}

DOUYIN_RESEARCH_SCRIPT_RESERVATION_SCHEMA = {
    "type": "object",
    "properties": {
        "aweme_id": {"type": "string"},
        "workflow": {"type": "string"},
        "status": {"type": "string", "enum": ["reserved", "used"]},
        "reservation_token": {"type": "string"},
        "reserved_at": {"type": "string"},
        "used_at": {"type": ["string", "null"]},
        "run_id": {"type": ["string", "null"]},
    },
    "required": ["aweme_id", "workflow", "status", "reservation_token", "reserved_at"],
    "additionalProperties": False,
}

DOUYIN_RESEARCH_SCRIPT_RESERVE_INPUT_SCHEMA = {
    "type": "object",
    "properties": {
        "collection_code": {"type": "string", "minLength": 1, "maxLength": 64},
        "workflow": {"type": "string", "minLength": 1, "maxLength": 64},
        "reservation_minutes": {"type": "integer", "minimum": 1, "maximum": 1440},
    },
    "required": ["collection_code", "workflow"],
    "additionalProperties": False,
}

DOUYIN_RESEARCH_SCRIPT_RESERVE_OUTPUT_SCHEMA = {
    "type": "object",
    "properties": {
        "source": DOUYIN_RESEARCH_SCRIPT_SOURCE_SCHEMA,
        "reservation": DOUYIN_RESEARCH_SCRIPT_RESERVATION_SCHEMA,
        "reservation_minutes": {"type": "integer", "minimum": 1},
    },
    "required": ["source", "reservation", "reservation_minutes"],
    "additionalProperties": False,
}

DOUYIN_RESEARCH_SCRIPT_USED_INPUT_SCHEMA = {
    "type": "object",
    "properties": {
        "aweme_id": {"type": "string", "pattern": "^\\d+$"},
        "workflow": {"type": "string", "minLength": 1, "maxLength": 64},
        "reservation_token": {"type": "string", "minLength": 1, "maxLength": 100},
        "run_id": {"type": "string", "minLength": 1, "maxLength": 100},
        "source_hook": {"type": "string", "minLength": 1, "maxLength": 2000},
    },
    "required": ["aweme_id", "workflow", "reservation_token", "run_id", "source_hook"],
    "additionalProperties": False,
}

DOUYIN_RESEARCH_SCRIPT_USED_OUTPUT_SCHEMA = {
    "type": "object",
    "properties": {
        "record": DOUYIN_RESEARCH_SCRIPT_RESERVATION_SCHEMA,
        "already_used": {"type": "boolean"},
    },
    "required": ["record", "already_used"],
    "additionalProperties": False,
}
