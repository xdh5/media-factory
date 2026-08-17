"""MatrixMedia CLI Tool 的输入输出 Schema。"""

from ._constants import HISTORY_STATUSES, LOGIN_PLATFORMS, PUBLISH_PLATFORMS, QUERY_PLATFORMS

ACCOUNT_PROPERTIES = {
    "phone": {"type": "string", "minLength": 1},
    "partition": {"type": "string", "minLength": 1},
}

PUBLISH_VIDEO_INPUT_SCHEMA = {
    "type": "object",
    "properties": {
        "platform": {"type": "string", "enum": PUBLISH_PLATFORMS},
        "video_path": {"type": "string"},
        "title": {"type": "string", "minLength": 1},
        **ACCOUNT_PROPERTIES,
        "short_title": {"type": "string"},
        "tags": {"type": "array", "maxItems": 4, "items": {"type": "string", "minLength": 1}},
        "task_name": {"type": "string"},
        "address": {"type": "string"},
        "publish_at": {"type": "string", "pattern": r"^\d{4}-\d{2}-\d{2} \d{2}:\d{2}:\d{2}$"},
        "draft": {"type": "boolean", "default": False},
        "sph_product_id": {"type": "string"},
    },
    "required": ["platform", "video_path", "title"],
    "oneOf": [
        {"required": ["phone"], "not": {"required": ["partition"]}},
        {"required": ["partition"], "not": {"required": ["phone"]}},
    ],
    "additionalProperties": False,
}

LIST_ACCOUNTS_INPUT_SCHEMA = {
    "type": "object",
    "properties": {
        "platform": {"type": "string", "enum": QUERY_PLATFORMS},
        "phone": {"type": "string"},
        "logged_in": {"type": "boolean"},
    },
    "additionalProperties": False,
}

LIST_HISTORY_INPUT_SCHEMA = {
    "type": "object",
    "properties": {
        "platform": {"type": "string", "enum": PUBLISH_PLATFORMS},
        "phone": {"type": "string"},
        "status": {"type": "string", "enum": HISTORY_STATUSES},
        "days": {"type": "integer", "minimum": 1, "default": 7},
        "limit": {"type": "integer", "minimum": 1, "default": 50},
        "since": {"type": "string", "pattern": r"^\d{4}-\d{2}-\d{2}$"},
        "until": {"type": "string", "pattern": r"^\d{4}-\d{2}-\d{2}$"},
    },
    "additionalProperties": False,
}

LOGIN_ACCOUNT_INPUT_SCHEMA = {
    "type": "object",
    "properties": {
        "platform": {"type": "string", "enum": LOGIN_PLATFORMS},
        **ACCOUNT_PROPERTIES,
        "timeout_seconds": {"type": "integer", "minimum": 30, "default": 900},
        "save_qr_png": {"type": "string"},
        "puppeteer_headless": {"type": "boolean", "default": False},
        "force": {"type": "boolean", "default": False},
    },
    "required": ["platform"],
    "oneOf": [
        {"required": ["phone"], "not": {"required": ["partition"]}},
        {"required": ["partition"], "not": {"required": ["phone"]}},
    ],
    "additionalProperties": False,
}

CLI_COMMAND_OUTPUT_SCHEMA = {
    "type": "object",
    "properties": {
        "success": {"type": "boolean"},
        "exit_code": {"type": "integer"},
        "command": {"type": "array", "items": {"type": "string"}},
        "stdout": {"type": "string"},
        "stderr": {"type": "string"},
    },
    "required": ["success", "exit_code", "command", "stdout", "stderr"],
    "additionalProperties": False,
}

CLI_JSON_OUTPUT_SCHEMA = {
    "description": "MatrixMedia CLI --json 的原始 JSON 结果，字段由 MatrixMedia CLI 版本决定",
    "oneOf": [{"type": "object"}, {"type": "array"}],
}

MATRIXMEDIA_ERROR_SCHEMA = {
    "type": "object",
    "properties": {
        "error": {
            "type": "object",
            "properties": {
                "code": {
                    "type": "string",
                    "enum": [
                        "INVALID_PARAMETER", "CLI_EXECUTABLE_NOT_FOUND",
                        "CLI_EXECUTION_FAILED", "CLI_OUTPUT_INVALID",
                        "ACCOUNT_DATABASE_ERROR", "ACCOUNT_NOT_FOUND",
                        "ACCOUNT_GROUP_NOT_FOUND",
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

REGISTER_ACCOUNT_INPUT_SCHEMA = {
    "type": "object",
    "properties": {
        "platform": {"type": "string", "enum": QUERY_PLATFORMS},
        **ACCOUNT_PROPERTIES,
        "alias": {"type": "string"},
    },
    "required": ["platform"],
    "oneOf": [
        {"required": ["phone"], "not": {"required": ["partition"]}},
        {"required": ["partition"], "not": {"required": ["phone"]}},
    ],
    "additionalProperties": False,
}

CREATE_ACCOUNT_GROUP_INPUT_SCHEMA = {
    "type": "object",
    "properties": {
        "name": {"type": "string", "minLength": 1},
        "account_ids": {
            "type": "array",
            "items": {"type": "integer", "minimum": 1},
            "uniqueItems": True,
            "default": [],
        },
    },
    "required": ["name"],
    "additionalProperties": False,
}

UPDATE_ACCOUNT_GROUP_MEMBERS_INPUT_SCHEMA = {
    "type": "object",
    "properties": {
        "group_id": {"type": "integer", "minimum": 1},
        "account_ids": {
            "type": "array",
            "minItems": 1,
            "items": {"type": "integer", "minimum": 1},
            "uniqueItems": True,
        },
    },
    "required": ["group_id", "account_ids"],
    "additionalProperties": False,
}

PUBLISH_TO_GROUP_INPUT_SCHEMA = {
    "type": "object",
    "properties": {
        "group_id": {"type": "integer", "minimum": 1},
        "video_path": {"type": "string"},
        "title": {"type": "string", "minLength": 1},
        "short_title": {"type": "string"},
        "tags": {"type": "array", "maxItems": 4, "items": {"type": "string"}},
        "task_name": {"type": "string"},
        "address": {"type": "string"},
        "publish_at": {"type": "string"},
        "draft": {"type": "boolean", "default": False},
    },
    "required": ["group_id", "video_path", "title"],
    "additionalProperties": False,
}

MIGRATE_WINDOWS_PROFILE_INPUT_SCHEMA = {
    "type": "object",
    "properties": {
        "source_user_data": {
            "type": "string",
            "description": "可选；默认读取当前 Windows 用户的 AppData/Roaming/matrix-video",
        },
        "database_path": {"type": "string", "description": "可选；默认使用项目统一数据库"},
    },
    "additionalProperties": False,
}

MIGRATE_WINDOWS_PROFILE_OUTPUT_SCHEMA = {
    "type": "object",
    "properties": {
        "source_user_data": {"type": "string"},
        "target_user_data": {"type": "string"},
        "copied_files": {"type": "integer"},
        "accounts": {"type": "array", "items": {"type": "object"}},
        "groups": {"type": "array", "items": {"type": "object"}},
    },
    "required": ["source_user_data", "target_user_data", "copied_files", "accounts", "groups"],
    "additionalProperties": False,
}
