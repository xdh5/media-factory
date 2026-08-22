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
        "usage": {
            "type": "object",
            "properties": {
                "prompt_tokens": {"type": "integer"},
                "completion_tokens": {"type": "integer"},
                "total_tokens": {"type": "integer"},
            },
            "additionalProperties": True,
        },
    },
    "required": ["text", "model", "finish_reason", "usage"],
    "additionalProperties": False,
}

QWEN_TEXT_ERROR_SCHEMA = {
    "type": "object",
    "properties": {
        "error": {
            "type": "object",
            "properties": {
                "code": {
                    "type": "string",
                    "enum": ["QWEN_TEXT_ERROR", "QWEN_CONFIGURATION_ERROR", "QWEN_REQUEST_ERROR", "QWEN_RESPONSE_ERROR"],
                },
                "message": {"type": "string"},
                "details": {"type": "object"},
            },
            "required": ["code", "message", "details"],
        }
    },
    "required": ["error"],
}

