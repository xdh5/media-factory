"""语言学习 MCP 工具的输入输出 Schema。"""

from ._constants import SUPPORTED_LEARNING_MODES

LEARNING_MODES_SCHEMA = {"type": "array", "minItems": 1, "maxItems": 2, "uniqueItems": True, "items": {"type": "string", "enum": list(SUPPORTED_LEARNING_MODES)}}
WORD_SCHEMA = {"type": "object", "properties": {"english": {"type": "string", "minLength": 1}, "chinese": {"type": "string", "minLength": 1}, "korean": {"type": "string", "minLength": 1}, "romanization": {"type": "string", "minLength": 1}}, "required": ["english", "chinese", "korean", "romanization"], "additionalProperties": False}

GET_TOPICS_INPUT_SCHEMA = {
    "type": "object",
    "properties": {"database_path": {"type": "string", "minLength": 1}},
    "additionalProperties": False,
}
VOCABULARY_PROMPT_INPUT_SCHEMA = {
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
    },
    "required": ["card_dirs", "words_by_mode", "run_id"],
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
GET_JOB_INPUT_SCHEMA = {
    "type": "object",
    "properties": {
        "job_id": {"type": "string", "pattern": r"^job-[0-9a-f]{32}$"},
        "database_path": {"type": "string"},
    },
    "required": ["job_id"],
    "additionalProperties": False,
}
LANGUAGE_LEARNING_ERROR_SCHEMA = {"type": "object", "properties": {"error": {"type": "object", "properties": {"code": {"type": "string", "enum": ["LANGUAGE_LEARNING_ERROR", "INVALID_VOCABULARY", "CARD_COMPOSITION_ERROR", "VOCABULARY_VIDEO_ERROR", "CONFIRMATION_REQUIRED", "PUBLISH_ERROR"]}, "message": {"type": "string"}, "details": {"type": "object"}}, "required": ["code", "message", "details"]}}, "required": ["error"]}
