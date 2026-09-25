"""抖音链接入库 MCP Schema。"""

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
            "const": "财经",
            "description": "写入数据库的分类名，目前仅支持“财经”",
        },
    },
    "required": ["share_text", "collection_name"],
    "additionalProperties": False,
}
