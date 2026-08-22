"""千问视觉理解输入输出 Schema。"""

ANALYZE_IMAGE_INPUT_SCHEMA = {
    "type": "object",
    "properties": {
        "image_path": {"type": "string", "minLength": 1},
        "system_prompt": {"type": "string", "minLength": 1},
        "user_prompt": {"type": "string", "minLength": 1},
        "max_image_width": {"type": "integer", "minimum": 64},
        "max_tokens": {"type": "integer", "minimum": 1},
        "json_output": {"type": "boolean", "default": False},
    },
    "required": ["image_path", "system_prompt", "user_prompt"],
    "additionalProperties": False,
}

ANALYZE_IMAGE_OUTPUT_SCHEMA = {
    "type": "object",
    "properties": {
        "text": {"type": "string"},
        "model": {"type": "string"},
        "finish_reason": {"type": ["string", "null"]},
        "image_size": {
            "type": "object",
            "properties": {
                "width": {"type": "integer"},
                "height": {"type": "integer"},
            },
            "required": ["width", "height"],
            "additionalProperties": False,
        },
        "usage": {"type": "object", "additionalProperties": True},
    },
    "required": ["text", "model", "finish_reason", "image_size", "usage"],
    "additionalProperties": False,
}

QWEN_VISION_ERROR_SCHEMA = {
    "type": "object",
    "properties": {
        "error": {
            "type": "object",
            "properties": {
                "code": {
                    "type": "string",
                    "enum": [
                        "QWEN_VISION_ERROR",
                        "QWEN_VISION_CONFIGURATION_ERROR",
                        "QWEN_VISION_REQUEST_ERROR",
                        "QWEN_VISION_RESPONSE_ERROR",
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
