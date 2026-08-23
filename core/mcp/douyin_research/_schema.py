"""抖音研究 MCP Schema。"""

SEARCH_INPUT_SCHEMA = {
    "type": "object",
    "properties": {
        "keyword": {"type": "string", "minLength": 1, "maxLength": 200},
        "limit": {"type": "integer", "minimum": 1, "maximum": 5, "default": 5},
    },
    "required": ["keyword"],
    "additionalProperties": False,
}
