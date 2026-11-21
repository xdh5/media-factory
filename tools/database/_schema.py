"""数据库接口数据合同。"""

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

PUBLICATION_RECORD_SCHEMA = {
    "type": "object",
    "properties": {
        "id": {"type": "integer"},
        "publication_id": {"type": "string"},
        "run_id": {"type": "string"},
        "business_line": {"type": "string", "enum": ["finance", "language_learning"]},
        "platform": {
            "type": "string",
            "enum": [
                "youtube", "facebook", "instagram", "tiktok", "kuaishou",
                "douyin", "baijiahao", "xiaohongshu", "toutiao", "wechat_channels",
            ],
        },
        "connector": {"type": "string"},
        "account_id": {"type": "string", "minLength": 1},
        "content_part": {"type": "integer", "minimum": 1},
        "title": {"type": "string"},
        "publish_mode": {"type": "string", "enum": ["immediate", "scheduled"]},
        "publish_at": {"type": "string", "format": "date-time"},
        "status": {"type": "string", "enum": ["published", "scheduled"]},
        "external_id": {"type": ["string", "null"]},
        "external_url": {"type": ["string", "null"]},
        "created_at": {"type": "string"},
        "updated_at": {"type": "string"},
    },
    "required": [
        "publication_id", "run_id", "business_line", "platform", "connector",
        "account_id", "content_part", "title", "publish_mode", "publish_at", "status",
    ],
    "additionalProperties": False,
}

PUBLICATION_RECORDS_COMMIT_INPUT_SCHEMA = {
    "type": "object",
    "properties": {
        "records": {
            "type": "array",
            "minItems": 1,
            "maxItems": 100,
            "items": PUBLICATION_RECORD_SCHEMA,
        },
    },
    "required": ["records"],
    "additionalProperties": False,
}

PUBLICATION_RECORDS_OUTPUT_SCHEMA = {
    "type": "object",
    "properties": {"records": {"type": "array", "items": PUBLICATION_RECORD_SCHEMA}},
    "required": ["records"],
    "additionalProperties": False,
}

PUBLISHING_ACCOUNT_GROUPS_OUTPUT_SCHEMA = {
    "type": "object",
    "properties": {
        "groups": {"type": "array", "items": {"type": "object"}},
        "members": {"type": "array", "items": {"type": "object"}},
    },
    "required": ["groups", "members"],
    "additionalProperties": False,
}

PRODUCTION_OUTPUT_SCHEMA = {
    "type": "object",
    "properties": {
        "id": {"type": "integer"},
        "production_id": {"type": "string"},
        "run_id": {"type": "string"},
        "publish_date": {"type": "string", "format": "date"},
        "business_line": {"type": "string", "enum": ["finance", "language_learning"]},
        "content_kind": {"type": "string"},
        "content_part": {"type": "integer", "minimum": 1},
        "title": {"type": "string"},
        "hashtags": {"type": "string"},
        "source": {"type": "string", "enum": ["local_mcp", "github_workflow"]},
        "local_path": {"type": ["string", "null"]},
        "r2_url": {"type": ["string", "null"]},
        "r2_expires_at": {"type": ["string", "null"], "format": "date-time"},
        "created_at": {"type": "string"},
        "updated_at": {"type": "string"},
    },
    "required": [
        "production_id", "run_id", "publish_date", "business_line", "content_kind",
        "content_part", "title", "hashtags", "source", "local_path", "r2_url", "r2_expires_at",
    ],
    "additionalProperties": False,
}

PRODUCTION_OUTPUTS_COMMIT_INPUT_SCHEMA = {
    "type": "object",
    "properties": {
        "records": {
            "type": "array",
            "minItems": 1,
            "maxItems": 100,
            "items": PRODUCTION_OUTPUT_SCHEMA,
        },
    },
    "required": ["records"],
    "additionalProperties": False,
}

PRODUCTION_OUTPUTS_OUTPUT_SCHEMA = {
    "type": "object",
    "properties": {"records": {"type": "array", "items": PRODUCTION_OUTPUT_SCHEMA}},
    "required": ["records"],
    "additionalProperties": False,
}

PRODUCTION_OUTPUTS_DELETE_INPUT_SCHEMA = {
    "type": "object",
    "properties": {
        "record_ids": {
            "type": "array",
            "minItems": 1,
            "maxItems": 100,
            "items": {"type": "integer", "minimum": 1},
        },
    },
    "required": ["record_ids"],
    "additionalProperties": False,
}

PRODUCTION_OUTPUTS_DELETE_OUTPUT_SCHEMA = {
    "type": "object",
    "properties": {"deleted_ids": {"type": "array", "items": {"type": "integer"}}},
    "required": ["deleted_ids"],
    "additionalProperties": False,
}

DATABASE_ERROR_SCHEMA = {
    "type": "object",
    "properties": {
        "error": {
            "type": "object",
            "properties": {
                "code": {
                    "type": "string",
                    "enum": [
                        "DATABASE_ERROR",
                        "DATABASE_CONFIGURATION_ERROR",
                        "DATABASE_REQUEST_ERROR",
                        "DATABASE_CONFLICT",
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


from ._constants import DEFAULT_DEDUPLICATION_DAYS, SUPPORTED_TOPIC_STATUSES

GET_TOPIC_INPUT_SCHEMA = {
    "type": "object",
    "properties": {
        "workflow": {"type": "string", "minLength": 1},
        "days": {"type": "integer", "minimum": 1, "default": DEFAULT_DEDUPLICATION_DAYS},
    },
    "required": ["workflow"],
    "additionalProperties": False,
}

UPDATE_TOPIC_INPUT_SCHEMA = {
    "type": "object",
    "properties": {
        "workflow": {"type": "string", "minLength": 1},
        "topic": {"type": "string", "minLength": 1},
        "days": {"type": "integer", "minimum": 1, "default": DEFAULT_DEDUPLICATION_DAYS},
    },
    "required": ["workflow", "topic"],
    "additionalProperties": False,
}

TOPIC_RECORD_SCHEMA = {
    "type": "object",
    "properties": {
        "id": {"type": "integer"},
        "workflow": {"type": "string"},
        "topic": {"type": "string"},
        "fingerprint": {"type": "string"},
        "status": {"type": "string", "enum": SUPPORTED_TOPIC_STATUSES},
        "created_at": {"type": "string"},
        "updated_at": {"type": "string"},
    },
    "required": ["id", "workflow", "topic", "fingerprint", "status", "created_at", "updated_at"],
    "additionalProperties": False,
}

GET_TOPIC_OUTPUT_SCHEMA = {
    "type": "array",
    "items": TOPIC_RECORD_SCHEMA,
}

UPDATE_TOPIC_OUTPUT_SCHEMA = TOPIC_RECORD_SCHEMA

COMMIT_TOPIC_INPUT_SCHEMA = {
    "type": "object",
    "properties": {
        "workflow": {"type": "string", "minLength": 1},
        "topic": {"type": "string", "minLength": 1},
        "publication_id": {"type": "string", "minLength": 1},
        "days": {"type": "integer", "minimum": 1},
        "entries": {"type": "array"},
        "history_days": {"type": "integer", "minimum": 1},
        "minimum_new_words": {"type": "integer", "minimum": 1, "maximum": 10},
    },
    "required": ["workflow", "topic", "publication_id"],
    "additionalProperties": False,
}

TOPIC_DEDUP_ERROR_SCHEMA = {
    "type": "object",
    "properties": {
        "error": {
            "type": "object",
            "properties": {
                "code": {
                    "type": "string",
                    "enum": ["INVALID_PARAMETER", "DUPLICATE_TOPIC", "TOPIC_DATA_SERVICE_ERROR"],
                },
                "message": {"type": "string"},
                "details": {"type": "object"},
            },
            "required": ["code", "message", "details"],
        },
    },
    "required": ["error"],
}
