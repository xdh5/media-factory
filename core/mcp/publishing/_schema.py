"""统一发布 MCP Schema。"""

BUSINESS_LINES = ["finance", "language_learning"]

ACCOUNT_GROUPS_QUERY_INPUT_SCHEMA = {
    "type": "object",
    "properties": {"business_line": {"type": "string", "enum": BUSINESS_LINES}},
    "additionalProperties": False,
}

PUBLISH_PREVIEW_INPUT_SCHEMA = {
    "type": "object",
    "properties": {
        "business_line": {"type": "string", "enum": BUSINESS_LINES},
        "publish_date": {"type": "string", "pattern": r"^\d{4}-\d{2}-\d{2}$"},
        "account_group": {"type": "string", "minLength": 1},
        "platforms": {"type": "array", "minItems": 1, "items": {"type": "string"}},
        "content_kind": {
            "type": ["string", "null"],
            "description": "language_learning 传 en-ko 会同时发布原版与问答版 en-ko-quiz",
        },
    },
    "required": ["business_line", "publish_date", "account_group", "platforms"],
    "additionalProperties": False,
}

PUBLISH_START_INPUT_SCHEMA = {
    "type": "object",
    "properties": {
        **PUBLISH_PREVIEW_INPUT_SCHEMA["properties"],
        "publish_mode": {"type": "string", "enum": ["immediate", "scheduled"]},
        "publish_at": {"type": "string", "minLength": 1},
        "publish_confirmed": {"type": "boolean", "const": True},
    },
    "required": [
        "business_line", "publish_date", "account_group", "platforms",
        "publish_mode", "publish_at", "publish_confirmed",
    ],
    "additionalProperties": False,
}

PUBLISH_RESULT_SCHEMA = {
    "type": "object",
    "properties": {
        "business_line": {"type": "string", "enum": BUSINESS_LINES},
        "publish_date": {"type": "string"},
        "publish_mode": {"type": "string", "enum": ["immediate", "scheduled"]},
        "publish_at": {"type": "string"},
        "published": {"type": "array", "items": {"type": "object"}},
        "skipped": {"type": "array", "items": {"type": "object"}},
    },
    "required": ["business_line", "publish_date", "publish_mode", "publish_at", "published", "skipped"],
    "additionalProperties": True,
}

TASK_POLL_INPUT_SCHEMA = {
    "type": "object",
    "properties": {"task_path": {"type": "string", "minLength": 1}},
    "required": ["task_path"],
    "additionalProperties": False,
}

__all__ = [
    "ACCOUNT_GROUPS_QUERY_INPUT_SCHEMA",
    "PUBLISH_PREVIEW_INPUT_SCHEMA",
    "PUBLISH_RESULT_SCHEMA",
    "PUBLISH_START_INPUT_SCHEMA",
    "TASK_POLL_INPUT_SCHEMA",
]
