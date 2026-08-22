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
