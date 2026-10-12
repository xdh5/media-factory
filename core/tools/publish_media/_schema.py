"""统一视频发布输入输出 Schema。"""

from ._constants import BUSINESS_LINES, PUBLISH_MODES, SUPPORTED_PLATFORMS

ACCOUNT_GROUPS_QUERY_INPUT_SCHEMA = {
    "type": "object",
    "properties": {"business_line": {"type": "string", "enum": list(BUSINESS_LINES)}},
    "additionalProperties": False,
}

PUBLISH_PREVIEW_INPUT_SCHEMA = {
    "type": "object",
    "properties": {
        "business_line": {"type": "string", "enum": list(BUSINESS_LINES)},
        "publish_date": {"type": "string", "pattern": r"^\d{4}-\d{2}-\d{2}$"},
        "account_group": {"type": "string", "minLength": 1},
        "platforms": {
            "type": "array",
            "minItems": 1,
            "uniqueItems": True,
            "items": {"type": "string"},
        },
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
        "publish_mode": {"type": "string", "enum": list(PUBLISH_MODES)},
        "publish_at": {"type": "string", "minLength": 1},
        "publish_at_by_platform": {
            "type": ["object", "null"],
            "additionalProperties": {"type": "string", "minLength": 1},
            "description": "按平台设置发布时间；值为 now 时立即发布，否则必须是带时区的 ISO 8601 时间",
        },
        "publish_confirmed": {"type": "boolean", "const": True},
    },
    "required": [
        "business_line", "publish_date", "account_group", "platforms",
        "publish_confirmed",
    ],
    "additionalProperties": False,
}

PUBLISH_RESULT_SCHEMA = {
    "type": "object",
    "properties": {
        "business_line": {"type": "string", "enum": list(BUSINESS_LINES)},
        "publish_date": {"type": "string"},
        "publish_mode": {"type": "string", "enum": [*PUBLISH_MODES, "per_platform"]},
        "publish_at": {"type": "string"},
        "published": {"type": "array", "items": {"type": "object"}},
        "skipped": {"type": "array", "items": {"type": "object"}},
    },
    "required": ["business_line", "publish_date", "publish_mode", "publish_at", "published", "skipped"],
    "additionalProperties": True,
}
