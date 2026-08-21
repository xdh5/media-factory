"""语言学习 MCP 工具的输入输出 Schema。"""

from ._constants import SUPPORTED_LEARNING_MODES

LEARNING_MODES_SCHEMA = {"type": "array", "minItems": 1, "maxItems": 2, "uniqueItems": True, "items": {"type": "string", "enum": list(SUPPORTED_LEARNING_MODES)}}
WORD_SCHEMA = {"type": "object", "properties": {"english": {"type": "string", "minLength": 1}, "chinese": {"type": "string", "minLength": 1}, "korean": {"type": "string", "minLength": 1}, "romanization": {"type": "string", "minLength": 1}}, "required": ["english", "chinese", "korean", "romanization"], "additionalProperties": False}
VOICES_SCHEMA = {
    "type": "object",
    "properties": {
        "en": {"type": "string", "minLength": 1},
        "zh": {"type": "string", "minLength": 1},
        "ko": {"type": "string", "minLength": 1},
    },
    "required": ["en", "zh", "ko"],
    "additionalProperties": False,
}
PUBLISH_MODE_SCHEMA = {
    "type": "object",
    "properties": {
        "account_group": {"type": "string", "minLength": 1},
        "tags": {"type": "array", "minItems": 1, "items": {"type": "string", "minLength": 1}},
        "short_title": {"type": "string", "minLength": 1},
        "youtube_account": {"type": "string", "minLength": 1},
        "platforms": {"type": "array", "items": {"type": "string", "minLength": 1}},
    },
    "additionalProperties": False,
}
PUBLISH_CONFIG_SCHEMA = {
    "type": "object",
    "minProperties": 1,
    "properties": {
        "en-zh": PUBLISH_MODE_SCHEMA,
        "en-ko": PUBLISH_MODE_SCHEMA,
    },
    "additionalProperties": False,
}

GET_TOPICS_INPUT_SCHEMA = {
    "type": "object",
    "properties": {"database_path": {"type": "string", "minLength": 1}},
    "additionalProperties": False,
}
OCCUPY_TOPIC_INPUT_SCHEMA = {
    "type": "object",
    "properties": {
        "topic": {"type": "string", "minLength": 1, "maxLength": 200},
        "learning_modes": LEARNING_MODES_SCHEMA,
        "database_path": {"type": "string", "minLength": 1},
    },
    "required": ["topic", "learning_modes"],
    "additionalProperties": False,
}
PARSE_VOCABULARY_INPUT_SCHEMA = {"type": "object", "properties": {"response_text": {"type": "string", "minLength": 1, "maxLength": 20000}, "learning_modes": LEARNING_MODES_SCHEMA}, "required": ["response_text", "learning_modes"], "additionalProperties": False}
BUILD_VOCABULARY_PROMPT_INPUT_SCHEMA = {
    "type": "object",
    "properties": {
        "topic": {"type": "string", "minLength": 1, "maxLength": 200},
        "learning_modes": LEARNING_MODES_SCHEMA,
    },
    "required": ["topic", "learning_modes"],
    "additionalProperties": False,
}
PREPARE_IMAGES_INPUT_SCHEMA = {
    "type": "object",
    "properties": {
        "topic": {"type": "string", "minLength": 1, "maxLength": 200},
        "words": {"type": "array", "minItems": 10, "maxItems": 10, "items": WORD_SCHEMA},
        "run_id": {"type": "string", "pattern": r"^run-\d{6,}$"},
        "force_images": {"type": "boolean", "default": False},
    },
    "required": ["topic", "words", "run_id"],
    "additionalProperties": False,
}
SUBMIT_IMAGES_INPUT_SCHEMA = {
    "type": "object",
    "properties": {
        "context_path": {"type": "string", "minLength": 1},
        "images": {
            "type": "array",
            "items": {
                "type": "object",
                "properties": {
                    "image_id": {"type": "string", "minLength": 1},
                    "image_path": {"type": "string", "minLength": 1},
                },
                "required": ["image_id", "image_path"],
                "additionalProperties": False,
            },
        },
        "failures": {
            "type": "array",
            "items": {
                "type": "object",
                "properties": {
                    "image_id": {"type": "string", "minLength": 1},
                    "attempts": {"type": "integer", "minimum": 0},
                    "capability_unavailable": {"type": "boolean", "default": False},
                    "errors": {"type": "array", "items": {"type": "string"}},
                },
                "required": ["image_id"],
                "additionalProperties": False,
            },
        },
    },
    "required": ["context_path", "images"],
    "additionalProperties": False,
}
COMPOSE_CARDS_INPUT_SCHEMA = {
    "type": "object",
    "properties": {
        "subject_sheet_path": {"type": "string", "minLength": 1},
        "words": {"type": "array", "minItems": 10, "maxItems": 10, "items": WORD_SCHEMA},
        "learning_mode": {"type": "string", "enum": list(SUPPORTED_LEARNING_MODES)},
        "topic_english": {"type": "string", "minLength": 1},
        "run_id": {"type": "string", "pattern": r"^run-\d{6,}$"},
    },
    "required": ["subject_sheet_path", "words", "learning_mode", "topic_english", "run_id"],
    "additionalProperties": False,
}
CREATE_VIDEOS_INPUT_SCHEMA = {
    "type": "object",
    "properties": {
        "card_dirs": {
            "type": "object",
            "minProperties": 1,
            "properties": {"en-ko": {"type": "string"}, "en-zh": {"type": "string"}},
            "additionalProperties": False,
        },
        "words_by_mode": {"type": "object"},
        "run_id": {"type": "string", "pattern": r"^run-\d{6,}$"},
        "topic": {"type": "string", "maxLength": 200},
        "language_pause": {"type": "number", "minimum": 0},
        "word_pause": {"type": "number", "minimum": 0},
        "voices": VOICES_SCHEMA,
        "publish_config": PUBLISH_CONFIG_SCHEMA,
    },
    "required": ["card_dirs", "words_by_mode", "run_id", "voices", "publish_config"],
    "additionalProperties": False,
}
PUBLISH_VIDEOS_INPUT_SCHEMA = {
    "type": "object",
    "properties": {
        "manifest_path": {"type": "string", "minLength": 1},
        "publish_confirmed": {"type": "boolean", "const": True},
    },
    "required": ["manifest_path", "publish_confirmed"],
    "additionalProperties": False,
}
CLEAR_RUN_INPUT_SCHEMA = {
    "type": "object",
    "properties": {
        "run_id": {"type": "string", "pattern": r"^run-\d{6,}$"},
        "confirmed": {"type": "boolean", "const": True},
    },
    "required": ["run_id", "confirmed"],
    "additionalProperties": False,
}
TASK_SUBMIT_OUTPUT_SCHEMA = {
    "type": "object",
    "properties": {
        "task_id": {"type": "string", "minLength": 1},
        "task_path": {"type": "string", "minLength": 1},
        "status": {"type": "string", "enum": ["running"]},
        "step": {"type": "string", "minLength": 1},
        "run_id": {"type": "string", "minLength": 1},
        "reused": {"type": "boolean"},
        "poll_tool": {"type": "string", "const": "language_learning_poll_task"},
    },
    "required": ["task_id", "task_path", "status", "step", "run_id", "poll_tool"],
    "additionalProperties": True,
}
TASK_POLL_OUTPUT_SCHEMA = {
    "type": "object",
    "properties": {
        "task_id": {"type": "string"},
        "task_path": {"type": "string"},
        "run_id": {"type": "string"},
        "step": {"type": "string"},
        "status": {"type": "string", "enum": ["running", "succeeded", "failed"]},
        "done": {"type": "boolean"},
        "duration_seconds": {"type": "number"},
        "progress": {"type": ["string", "null"]},
        "result": {"type": ["object", "null"]},
        "error": {"type": ["object", "null"]},
    },
    "required": ["task_id", "status", "done"],
    "additionalProperties": True,
}
TASK_POLL_INPUT_SCHEMA = {
    "type": "object",
    "properties": {"task_path": {"type": "string", "minLength": 1}},
    "required": ["task_path"],
    "additionalProperties": False,
}
LANGUAGE_LEARNING_ERROR_SCHEMA = {"type": "object", "properties": {"error": {"type": "object", "properties": {"code": {"type": "string", "enum": ["LANGUAGE_LEARNING_ERROR", "INVALID_VOCABULARY", "CARD_COMPOSITION_ERROR", "VOCABULARY_VIDEO_ERROR", "CONFIRMATION_REQUIRED", "PUBLISH_ERROR"]}, "message": {"type": "string"}, "details": {"type": "object"}}, "required": ["code", "message", "details"]}}, "required": ["error"]}
