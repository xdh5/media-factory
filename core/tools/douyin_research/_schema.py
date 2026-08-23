"""抖音研究工具 Schema。"""

SEARCH_INPUT_SCHEMA = {
    "type": "object",
    "properties": {
        "keyword": {"type": "string", "minLength": 1, "maxLength": 200},
        "limit": {"type": "integer", "minimum": 1, "maximum": 5, "default": 5},
    },
    "required": ["keyword"],
    "additionalProperties": False,
}

TRANSCRIPT_REVIEW_SCHEMA = {
    "type": "object",
    "properties": {
        "number": {"type": "integer", "minimum": 1, "maximum": 5},
        "text": {"type": "string", "minLength": 1, "maxLength": 50000},
    },
    "required": ["number", "text"],
    "additionalProperties": False,
}

COMMIT_INPUT_SCHEMA = {
    "type": "object",
    "properties": {
        "context_path": {"type": "string", "minLength": 1},
        "candidate_numbers": {
            "type": "array",
            "items": {"type": "integer", "minimum": 1, "maximum": 5},
            "minItems": 1,
            "uniqueItems": True,
        },
        "confirmed": {"type": "boolean", "const": True},
    },
    "required": ["context_path", "candidate_numbers", "confirmed"],
    "additionalProperties": False,
}
