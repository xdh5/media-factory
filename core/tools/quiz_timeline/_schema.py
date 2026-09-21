"""心灵鸡汤时间轴工具输入输出结构。"""

QUIZ_STAGE_SCHEMA = {
    "type": "object",
    "properties": {
        "label": {"type": "string", "enum": ["A", "B", "C", "D"]},
        "start": {"type": "number", "minimum": 0},
        "end": {"type": "number", "exclusiveMinimum": 0},
    },
    "required": ["label", "start", "end"],
    "additionalProperties": False,
}

QUIZ_CHAPTER_SCHEMA = {
    "type": "object",
    "properties": {
        "title": {"type": "string", "minLength": 1},
        "start": {"type": "number", "minimum": 0},
        "end": {"type": "number", "exclusiveMinimum": 0},
    },
    "required": ["title", "start", "end"],
    "additionalProperties": False,
}

GENERATE_QUIZ_TIMELINE_INPUT_SCHEMA = {
    "type": "object",
    "properties": {
        "output_path": {"type": "string", "minLength": 1},
        "duration": {"type": "number", "exclusiveMinimum": 0},
        "option_stages": {"type": "array", "minItems": 4, "maxItems": 4, "items": QUIZ_STAGE_SCHEMA},
        "result_stages": {"type": "array", "minItems": 4, "maxItems": 4, "items": QUIZ_STAGE_SCHEMA},
        "chapters": {"type": "array", "minItems": 2, "items": QUIZ_CHAPTER_SCHEMA},
        "position": {"type": "string", "enum": ["bottom", "top"], "default": "bottom"},
    },
    "required": ["output_path", "duration", "option_stages", "result_stages", "chapters"],
    "additionalProperties": False,
}
