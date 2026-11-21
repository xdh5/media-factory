"""数据库接口数据合同。"""

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

SCENARIO_QUIZ_CATEGORIES = ["finance", "success", "human_nature"]

SCENARIO_QUIZ_QUESTION_SCHEMA = {
    "type": "object",
    "properties": {
        "id": {"type": "integer"},
        "run_id": {"type": "string"},
        "topic_record_id": {"type": "integer"},
        "topic": {"type": "string"},
        "category": {"type": "string", "enum": SCENARIO_QUIZ_CATEGORIES},
        "scene_title": {"type": "string"},
        "scenario": {"type": "string"},
        "option_a": {"type": "string"},
        "option_b": {"type": "string"},
        "option_c": {"type": "string"},
        "option_d": {"type": "string"},
        "result_a": {"type": "string"},
        "result_b": {"type": "string"},
        "result_c": {"type": "string"},
        "result_d": {"type": "string"},
        "image_keywords": {"type": "array", "items": {"type": "string"}},
        "status": {"type": "string", "enum": ["reserved", "used", "rejected"]},
        "publish_date": {"type": "string", "format": "date"},
    },
    "required": [
        "run_id", "topic_record_id", "topic", "category", "scene_title", "scenario",
        "option_a", "option_b", "option_c", "option_d", "result_a", "result_b",
        "result_c", "result_d", "image_keywords", "status", "publish_date",
    ],
    "additionalProperties": False,
}

SCENARIO_QUIZ_COMMIT_INPUT_SCHEMA = {
    "type": "object",
    "properties": {"record": SCENARIO_QUIZ_QUESTION_SCHEMA},
    "required": ["record"],
    "additionalProperties": False,
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
