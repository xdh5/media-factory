"""抖音研究 MCP Schema。"""

SEARCH_INPUT_SCHEMA = {
    "type": "object",
    "properties": {
        "keyword": {"type": "string", "minLength": 1, "maxLength": 200},
        "collection_code": {"type": "string", "pattern": "^[a-z][a-z0-9_-]{0,63}$"},
        "collection_name": {"type": "string", "minLength": 1, "maxLength": 100},
        "limit": {"type": "integer", "minimum": 1, "maximum": 5, "default": 5},
    },
    "required": ["keyword", "collection_code", "collection_name"],
    "additionalProperties": False,
}
