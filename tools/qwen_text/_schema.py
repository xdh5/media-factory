"""千问文本生成输入输出 Schema。"""

GENERATE_TEXT_INPUT_SCHEMA = {
    "type": "object",
    "properties": {
        "system_prompt": {"type": "string", "minLength": 1},
        "user_prompt": {"type": "string", "minLength": 1},
        "temperature": {"type": "number", "minimum": 0, "maximum": 2},
        "max_tokens": {"type": "integer", "minimum": 1},
        "json_output": {"type": "boolean", "default": False},
    },
    "required": ["system_prompt", "user_prompt"],
    "additionalProperties": False,
}

GENERATE_TEXT_OUTPUT_SCHEMA = {
    "type": "object",
    "properties": {
        "text": {"type": "string"},
        "model": {"type": "string"},
        "finish_reason": {"type": ["string", "null"]},
        "usage": {"type": "object", "additionalProperties": True},
    },
    "required": ["text", "model", "finish_reason", "usage"],
    "additionalProperties": False,
}

QWEN_TEXT_ERROR_SCHEMA = {
    "type": "object",
    "properties": {"error": {"type": "object"}},
    "required": ["error"],
}
