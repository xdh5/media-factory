"""财经工作流输入输出 Schema。"""

FINANCE_WORKFLOW_INPUT_SCHEMA = {
    "type": "object",
    "properties": {
        "database_path": {"type": "string", "description": "可选；默认使用项目统一数据库 data/media_factory.sqlite3"},
        "draft_path": {"type": "string", "description": "用户确认稿件后，传入首次运行返回的 draft_path 继续执行"},
        "article_confirmed": {"type": "boolean", "default": False, "description": "仅在用户明确确认 draft_path 对应稿件后传 true"},
        "storyboard_text": {"type": "string", "minLength": 1, "description": "Trae 根据分镜提示生成的完整分镜文本；传入后不调用私有 Agent 文本回调"},
        "force_shot_ids": {"type": "array", "items": {"type": "string"}, "uniqueItems": True},
        "force_images": {"type": "boolean", "default": False},
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
        "created_at": {"type": "string", "format": "date-time"},
        "product_record_id": {"type": "integer", "minimum": 1},
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
                        "PRODUCT_NOT_FOUND", "PRODUCT_DELETION_ERROR",
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
        "user_confirmed": {"type": "boolean", "const": True},
        "force_shot_ids": {"type": "array", "items": {"type": "string"}, "uniqueItems": True},
        "force_images": {"type": "boolean", "default": False},
    },
    "required": ["draft_path", "storyboard_text", "user_confirmed"],
    "additionalProperties": False,
}

FINANCE_PUBLISH_INPUT_SCHEMA = {
    "type": "object",
    "properties": {
        "manifest_path": {"type": "string", "minLength": 1},
        "publish_confirmed": {"type": "boolean", "const": True},
        "account_group_name": {"type": "string", "minLength": 1, "default": "心灵鸡汤"},
    },
    "required": ["manifest_path", "publish_confirmed"],
    "additionalProperties": False,
}

DELETE_FINANCE_PRODUCT_INPUT_SCHEMA = {
    "type": "object",
    "properties": {
        "product_record_id": {"type": "integer", "minimum": 1},
        "delete_cache": {"type": "boolean", "default": True},
        "database_path": {"type": "string", "description": "可选；默认使用项目统一数据库"},
    },
    "required": ["product_record_id"],
    "additionalProperties": False,
}

DELETE_FINANCE_CACHE_INPUT_SCHEMA = {
    "type": "object",
    "properties": {
        "product_record_id": {"type": "integer", "minimum": 1},
        "database_path": {"type": "string", "description": "可选；默认使用项目统一数据库"},
    },
    "required": ["product_record_id"],
    "additionalProperties": False,
}

DELETE_FINANCE_PRODUCT_OUTPUT_SCHEMA = {
    "type": "object",
    "properties": {
        "product_record_id": {"type": "integer"},
        "run_id": {"type": "string"},
        "output_deleted": {"type": "boolean"},
        "cache_deleted": {"type": "boolean"},
        "deleted_at": {"type": ["string", "null"]},
    },
    "required": ["product_record_id", "run_id", "output_deleted", "cache_deleted", "deleted_at"],
    "additionalProperties": False,
}
