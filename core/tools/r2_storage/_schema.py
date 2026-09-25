"""Cloudflare R2 对象存储输入输出 Schema。"""

UPLOAD_PUBLIC_FILE_INPUT_SCHEMA = {
    "type": "object",
    "properties": {
        "file_path": {"type": "string", "minLength": 1},
        "object_key": {"type": "string", "minLength": 1, "maxLength": 512},
        "content_type": {"type": "string", "minLength": 1},
    },
    "required": ["file_path", "object_key"],
    "additionalProperties": False,
}

UPLOAD_PUBLIC_FILE_OUTPUT_SCHEMA = {
    "type": "object",
    "properties": {
        "url": {"type": "string", "minLength": 1},
        "key": {"type": "string"},
        "bucket": {"type": "string"},
        "size": {"type": "integer"},
    },
    "required": ["url", "key", "bucket", "size"],
    "additionalProperties": False,
}

DOWNLOAD_PUBLIC_FILE_INPUT_SCHEMA = {
    "type": "object",
    "properties": {
        "object_key": {"type": "string", "minLength": 1, "maxLength": 512},
        "destination_path": {"type": "string", "minLength": 1},
    },
    "required": ["object_key", "destination_path"],
    "additionalProperties": False,
}

DOWNLOAD_PUBLIC_FILE_OUTPUT_SCHEMA = {
    "type": "object",
    "properties": {
        "path": {"type": "string", "minLength": 1},
        "key": {"type": "string"},
        "bucket": {"type": "string"},
        "size": {"type": "integer", "minimum": 1},
    },
    "required": ["path", "key", "bucket", "size"],
    "additionalProperties": False,
}

DELETE_PUBLIC_FILES_INPUT_SCHEMA = {
    "type": "object",
    "properties": {
        "object_keys": {
            "type": "array",
            "minItems": 1,
            "maxItems": 1000,
            "items": {"type": "string", "minLength": 1, "maxLength": 512},
        },
    },
    "required": ["object_keys"],
    "additionalProperties": False,
}

DELETE_PUBLIC_FILES_OUTPUT_SCHEMA = {
    "type": "object",
    "properties": {
        "deleted": {"type": "boolean"},
        "keys": {"type": "array", "items": {"type": "string"}},
        "bucket": {"type": "string"},
    },
    "required": ["deleted", "keys", "bucket"],
    "additionalProperties": False,
}
