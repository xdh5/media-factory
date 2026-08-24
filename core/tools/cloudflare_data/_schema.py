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

DOUYIN_RESEARCH_SCRIPT_STATS_INPUT_SCHEMA = {
    "type": "object",
    "properties": {
        "collection_code": {"type": "string", "minLength": 1, "maxLength": 64},
        "workflow": {"type": "string", "minLength": 1, "maxLength": 64},
        "reservation_minutes": {"type": "integer", "minimum": 1, "maximum": 1440},
    },
    "required": ["collection_code", "workflow"],
    "additionalProperties": False,
}

DOUYIN_RESEARCH_SCRIPT_STATS_OUTPUT_SCHEMA = {
    "type": "object",
    "properties": {
        "collection_code": {"type": "string"},
        "workflow": {"type": "string"},
        "reservation_minutes": {"type": "integer", "minimum": 1},
        "total_count": {"type": "integer", "minimum": 0},
        "available_count": {"type": "integer", "minimum": 0},
        "reserved_count": {"type": "integer", "minimum": 0},
        "used_count": {"type": "integer", "minimum": 0},
        "checked_at": {"type": "string"},
    },
    "required": [
        "collection_code",
        "workflow",
        "reservation_minutes",
        "total_count",
        "available_count",
        "reserved_count",
        "used_count",
        "checked_at",
    ],
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
