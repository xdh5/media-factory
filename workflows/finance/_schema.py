"""财经工作流输入输出 Schema。"""

FINANCE_WORKFLOW_INPUT_SCHEMA = {
    "type": "object",
    "properties": {
        "database_path": {"type": "string", "description": "可选；默认使用项目统一数据库 data/media_factory.sqlite3"},
        "draft_path": {"type": "string", "description": "用户确认稿件后，传入首次运行返回的 draft_path 继续执行"},
        "article_confirmed": {"type": "boolean", "default": False, "description": "仅在用户明确确认 draft_path 对应稿件后传 true"},
        "storyboard_text": {"type": "string", "minLength": 1, "description": "当前 Agent 根据分镜提示生成的完整分镜文本；传入后不调用私有 Agent 文本回调"},
        "image_manifest_path": {"type": "string", "description": "finance_submit_images 返回的当前 Agent 生图清单"},
        "force_shot_ids": {"type": "array", "items": {"type": "string"}, "uniqueItems": True},
    },
    "additionalProperties": False,
}

FINANCE_WORKFLOW_OUTPUT_SCHEMA = {
    "type": "object",
    "properties": {
        "version": {"type": "integer", "minimum": 1},
        "status": {
            "type": "string",
            "enum": ["awaiting_article_confirmation", "awaiting_publish_confirmation"],
        },
        "confirmation_required": {"type": "string", "enum": ["article", "publish"]},
        "database_path": {"type": "string"},
        "topic": {"type": "string"},
        "run_id": {"type": "string", "pattern": r"^run-\d{6,}$"},
        "article": {"type": "string"},
        "title": {"type": "string"},
        "short_title": {"type": "string"},
        "hashtags": {"type": "array", "minItems": 4, "maxItems": 4, "items": {"type": "string"}},
        "cover_path": {"type": "string"},
        "video_path": {"type": "string"},
        "output_dir": {"type": "string"},
        "cache_dir": {"type": "string"},
        "title_path": {"type": "string"},
        "publish_copy": {"type": "string"},
        "publish_copy_path": {"type": "string"},
        "matrixmedia_account_group": {"type": "string"},
        "created_at": {"type": "string", "format": "date-time"},
        "manifest_path": {"type": "string"},
        "draft_path": {"type": "string"},
        "topic_record_id": {"type": "integer"},
        "shots": {"type": "array", "items": {"type": "object"}},
    },
    "required": ["status", "confirmation_required", "topic", "run_id", "article", "title", "short_title", "hashtags", "output_dir", "topic_record_id"],
    "additionalProperties": False,
}

FINANCE_WORKFLOW_ERROR_SCHEMA = {
    "type": "object",
    "properties": {
        "error": {
            "type": "object",
            "properties": {
                "code": {
                    "type": "string",
                    "enum": [
                        "FINANCE_WORKFLOW_ERROR", "AGENT_TEXT_CAPABILITY_ERROR",
                        "AGENT_OUTPUT_FORMAT_ERROR", "WORKFLOW_STEP_ERROR",
                        "CONFIRMATION_REQUIRED", "DRAFT_NOT_FOUND",
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

FINANCE_SAVE_DRAFT_INPUT_SCHEMA = {
    "type": "object",
    "properties": {
        "topic": {"type": "string", "minLength": 1},
        "article": {"type": "string", "minLength": 1},
        "title": {"type": "string", "minLength": 12, "maxLength": 26},
        "short_title": {"type": "string", "minLength": 6, "maxLength": 16},
        "hashtags": {"type": "array", "minItems": 4, "maxItems": 4, "uniqueItems": True, "items": {"type": "string", "minLength": 1}},
        "database_path": {"type": "string"},
        "draft_path": {"type": "string", "description": "修改已生成稿件时传入原 draft_path；话题不得改变"},
    },
    "required": ["topic", "article", "title", "short_title", "hashtags"],
    "additionalProperties": False,
}

FINANCE_PREPARE_STORYBOARD_INPUT_SCHEMA = {
    "type": "object",
    "properties": {
        "draft_path": {"type": "string", "minLength": 1},
        "user_confirmed": {"type": "boolean", "const": True},
    },
    "required": ["draft_path", "user_confirmed"],
    "additionalProperties": False,
}

FINANCE_FINISH_VIDEO_INPUT_SCHEMA = {
    "type": "object",
    "properties": {
        "draft_path": {"type": "string", "minLength": 1},
        "storyboard_text": {"type": "string", "minLength": 1},
        "image_manifest_path": {"type": "string", "minLength": 1},
        "user_confirmed": {"type": "boolean", "const": True},
        "force_shot_ids": {"type": "array", "items": {"type": "string"}, "uniqueItems": True},
    },
    "required": ["draft_path", "storyboard_text", "image_manifest_path", "user_confirmed"],
    "additionalProperties": False,
}

FINANCE_PREPARE_IMAGES_INPUT_SCHEMA = {
    "type": "object",
    "properties": {
        "draft_path": {"type": "string", "minLength": 1},
        "storyboard_text": {"type": "string", "minLength": 1},
        "user_confirmed": {"type": "boolean", "const": True},
        "force_image_ids": {"type": "array", "items": {"type": "string"}, "uniqueItems": True},
        "force_images": {"type": "boolean", "default": False},
    },
    "required": ["draft_path", "storyboard_text", "user_confirmed"],
    "additionalProperties": False,
}

FINANCE_SUBMIT_IMAGES_INPUT_SCHEMA = {
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
                    "capability_unavailable": {"type": "boolean"},
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

FINANCE_JOB_OUTPUT_SCHEMA = {
    "type": "object",
    "properties": {
        "job_id": {"type": "string", "pattern": r"^job-[0-9a-f]{32}$"},
        "workflow": {"type": "string"},
        "job_type": {
            "type": "string",
            "enum": ["prepare_storyboard", "submit_images", "finish_video"],
        },
        "status": {"type": "string", "enum": ["queued", "running", "completed", "failed"]},
        "progress_message": {"type": "string"},
        "result": {"type": ["object", "null"]},
        "error": {"type": ["object", "null"]},
        "created_at": {"type": "string", "format": "date-time"},
        "started_at": {"type": ["string", "null"], "format": "date-time"},
        "finished_at": {"type": ["string", "null"], "format": "date-time"},
        "updated_at": {"type": "string", "format": "date-time"},
    },
    "required": [
        "job_id", "workflow", "job_type", "status", "progress_message", "result", "error",
        "created_at", "started_at", "finished_at", "updated_at",
    ],
    "additionalProperties": False,
}

FINANCE_GET_JOB_INPUT_SCHEMA = {
    "type": "object",
    "properties": {
        "job_id": {"type": "string", "pattern": r"^job-[0-9a-f]{32}$"},
        "database_path": {"type": "string", "description": "可选；默认使用项目统一数据库"},
    },
    "required": ["job_id"],
    "additionalProperties": False,
}
