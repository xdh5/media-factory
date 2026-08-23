"""抖音链接入库工具 Schema。"""

INGEST_INPUT_SCHEMA = {
    "type": "object",
    "properties": {
        "share_text": {
            "type": "string",
            "minLength": 1,
            "description": "抖音分享链接或包含链接的分享文字",
        },
        "collection_name": {
            "type": "string",
            "minLength": 1,
            "maxLength": 100,
            "description": "写入数据库的中文分类名",
        },
    },
    "required": ["share_text", "collection_name"],
    "additionalProperties": False,
}

INGEST_OUTPUT_SCHEMA = {
    "type": "object",
    "properties": {
        "aweme_id": {"type": "string"},
        "collection_code": {"type": "string"},
        "collection_name": {"type": "string"},
        "transcript": {"type": "string"},
        "video_path": {"type": "string"},
        "database": {"type": "object"},
    },
    "required": [
        "aweme_id",
        "collection_code",
        "collection_name",
        "transcript",
        "video_path",
        "database",
    ],
    "additionalProperties": False,
}
