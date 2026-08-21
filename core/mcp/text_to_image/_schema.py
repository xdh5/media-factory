"""文生图 MCP 输入输出 Schema。"""

TTS_CONFIG_SCHEMA = {
    "type": "object",
    "properties": {
        "voice": {"type": "string", "minLength": 1},
        "rate": {"type": "string", "minLength": 1},
        "trim_trailing_silence": {"type": "boolean"},
    },
    "required": ["voice", "rate", "trim_trailing_silence"],
    "additionalProperties": False,
}
IMAGE_CONFIG_SCHEMA = {
    "type": "object",
    "properties": {
        "source": {"type": "string", "enum": ["local_library"]},
        "library_line": {"type": "string", "minLength": 1},
    },
    "required": ["source"],
    "additionalProperties": False,
}
PRODUCTION_CONFIG_SCHEMA = {
    "type": "object",
    "properties": {
        "bgm_path": {"type": "string", "minLength": 1},
        "cover_frame_seconds": {"type": "number", "minimum": 0},
        "intro": {"type": "string", "minLength": 1},
        "intro_sfx_path": {"type": "string"},
        "shot_stickers": {"type": "array", "minItems": 1, "items": {"type": "string", "minLength": 1}},
        "matrixmedia_account_group": {"type": "string", "minLength": 1},
    },
    "required": ["bgm_path", "cover_frame_seconds", "intro", "shot_stickers", "matrixmedia_account_group"],
    "additionalProperties": False,
}
TEXT_TO_IMAGE_SAVE_DRAFT_INPUT_SCHEMA = {
    "type": "object",
    "properties": {
        "topic": {"type": "string", "minLength": 1},
        "article": {"type": "string", "minLength": 1},
        "title": {"type": "string", "minLength": 12, "maxLength": 26},
        "short_title": {"type": "string", "minLength": 6, "maxLength": 16},
        "hashtags": {
            "type": "array",
            "minItems": 4,
            "maxItems": 4,
            "uniqueItems": True,
            "items": {"type": "string", "minLength": 1},
        },
        "database_path": {"type": "string"},
        "draft_path": {"type": "string", "description": "修改已生成稿件时传入原 draft_path；话题不得改变"},
        "cover_lines": {
            "type": "array",
            "minItems": 1,
            "maxItems": 3,
            "items": {"type": "string", "minLength": 1},
            "description": "封面用长标题的断行，由 Agent 按语义拆行，拼接后必须等于 title",
        },
    },
    "required": ["topic", "article", "title", "short_title", "hashtags", "cover_lines"],
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
        "poll_tool": {"type": "string", "const": "text_to_image_poll_task"},
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
