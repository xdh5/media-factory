"""话题历史工具 JSON Schema。"""

from __future__ import annotations

from ._constants import DEFAULT_DEDUPLICATION_DAYS, SUPPORTED_TOPIC_STATUSES

RECENT_TOPICS_INPUT_SCHEMA = {
    "type": "object",
    "properties": {
        "database_path": {"type": "string"},
        "workflow": {"type": "string", "minLength": 1},
        "days": {"type": "integer", "minimum": 1, "default": DEFAULT_DEDUPLICATION_DAYS},
    },
    "required": ["database_path", "workflow"],
    "additionalProperties": False,
}

RESERVE_TOPIC_INPUT_SCHEMA = {
    "type": "object",
    "properties": {
        "database_path": {"type": "string"},
        "workflow": {"type": "string", "minLength": 1},
        "topic": {"type": "string", "minLength": 1},
        "days": {"type": "integer", "minimum": 1, "default": DEFAULT_DEDUPLICATION_DAYS},
    },
    "required": ["database_path", "workflow", "topic"],
    "additionalProperties": False,
}

UPDATE_TOPIC_STATUS_INPUT_SCHEMA = {
    "type": "object",
    "properties": {
        "database_path": {"type": "string"},
        "record_id": {"type": "integer", "minimum": 1},
        "status": {"type": "string", "enum": SUPPORTED_TOPIC_STATUSES},
    },
    "required": ["database_path", "record_id", "status"],
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

RECENT_TOPICS_OUTPUT_SCHEMA = {
    "type": "array",
    "items": TOPIC_RECORD_SCHEMA,
}

RESERVE_TOPIC_OUTPUT_SCHEMA = TOPIC_RECORD_SCHEMA
UPDATE_TOPIC_STATUS_OUTPUT_SCHEMA = TOPIC_RECORD_SCHEMA

TOPIC_HISTORY_ERROR_SCHEMA = {
    "type": "object",
    "properties": {
        "error": {
            "type": "object",
            "properties": {
                "code": {
                    "type": "string",
                    "enum": [
                        "INVALID_PARAMETER", "DUPLICATE_TOPIC",
                        "TOPIC_RECORD_NOT_FOUND", "TOPIC_DATABASE_ERROR",
                    ],
                },
                "message": {"type": "string"},
                "details": {"type": "object"},
            },
            "required": ["code", "message", "details"],
        },
    },
    "required": ["error"],
}
