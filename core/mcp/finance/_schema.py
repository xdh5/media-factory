"""财经 MCP 输入输出 Schema。"""

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
        "source": {"type": "string", "enum": ["local_library", "qwen_reference"]},
        "library_line": {"type": "string", "enum": ["finance"]},
        "reference_image_path": {"type": "string", "minLength": 1},
    },
    "required": ["source"],
    "additionalProperties": False,
}

FINANCE_QWEN_IMAGE_TASK_INPUT_SCHEMA = {
    "type": "object",
    "properties": {
        "context_path": {"type": "string", "minLength": 1},
    },
    "required": ["context_path"],
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
        "subtitle_position": {
            "type": "object",
            "properties": {
                "alignment": {"type": "integer", "enum": [5]},
                "margin_vertical_ratio": {"type": "number", "minimum": 0, "maximum": 1},
            },
            "required": ["alignment", "margin_vertical_ratio"],
            "additionalProperties": False,
        },
        "subtitle_style": {
            "type": "object",
            "properties": {
                "preset": {"type": "string", "enum": ["karaoke"]},
                "highlight_color": {"type": "string", "enum": ["#FFD54A"]},
                "font_size": {"type": "number", "minimum": 8},
            },
            "required": ["preset", "highlight_color"],
            "additionalProperties": False,
        },
        "bgm_gain": {"type": "number", "exclusiveMinimum": 0},
        "secondary_subtitles": {
            "type": "object",
            "description": "中文下方的英文翻译字幕层（默认开启，字号=中文字号×0.4）",
            "properties": {
                "enabled": {"type": "boolean"},
                "font_size_ratio": {"type": "number", "minimum": 0.1, "maximum": 1},
                "style": {"type": "object"},
                "position": {"type": "object"},
            },
            "additionalProperties": False,
        },
        "matrixmedia_account_group": {"type": "string", "minLength": 1},
        "chapter_timeline": {
            "type": "object",
            "description": "章节时间轴条（贴在画面上方/下方，段落标题 AI 生成，进度色随播放推进）",
            "properties": {
                "enabled": {"type": "boolean"},
                "position": {"type": "string", "enum": ["top", "bottom"]},
                "segment_count": {"type": "integer", "minimum": 2, "maximum": 12},
                "ai_titles": {"type": "boolean"},
                "font_size": {"type": "number", "minimum": 8},
                "bar_height": {"type": "number", "minimum": 16},
                "margin_horizontal": {"type": "number", "minimum": 0},
                "margin_vertical_ratio": {"type": "number", "minimum": 0, "maximum": 0.4},
            },
            "additionalProperties": False,
        },
        "emphasis_lines": {
            "type": "object",
            "description": "重点句大字层：交互式生产由宿主 Agent 传 groups；GitHub Action 无宿主时才调用文本模型 API",
            "properties": {
                "enabled": {"type": "boolean"},
                "font_size": {"type": "number", "minimum": 24},
                "primary_color": {"type": "string"},
                "highlight_color": {"type": "string"},
                "outline_color": {"type": "string"},
                "outline": {"type": "number", "minimum": 0},
                "bold": {"type": "boolean"},
                "center_ratio": {"type": "number", "exclusiveMinimum": 0, "exclusiveMaximum": 1},
                "line_height": {"type": "number", "minimum": 1.0, "maximum": 2.5},
                "animations": {"type": "array", "minItems": 1, "items": {"type": "string"}},
                "animation_duration": {"type": "number", "exclusiveMinimum": 0},
                "bottom_position": {"type": "object"},
                "ai_detect": {"type": "boolean"},
                "groups": {
                    "type": ["array", "null"],
                    "description": "宿主 Agent 判断的重点句、语义断行和逐行标红词；每个显示行必须至少有一个原文重点词",
                },
                "seed": {"type": ["integer", "null"]},
            },
            "additionalProperties": False,
        },
    },
    "required": ["bgm_path", "cover_frame_seconds", "intro", "shot_stickers", "matrixmedia_account_group"],
    "additionalProperties": False,
}
UPLOAD_R2_INPUT_SCHEMA = {
    "type": "object",
    "properties": {
        "manifest_path": {"type": "string", "minLength": 1},
        "run_id": {"type": "string", "pattern": r"^run-\d{6,}$"},
    },
    "required": ["manifest_path", "run_id"],
    "additionalProperties": False,
}
PUBLICATION_RECORDS_INPUT_SCHEMA = {
    "type": "object",
    "properties": {
        "publication_id": {"type": "string", "minLength": 1},
        "run_id": {"type": "string", "minLength": 1},
        "records": {"type": "array", "minItems": 1, "items": {"type": "object"}},
    },
    "required": ["publication_id", "run_id", "records"],
    "additionalProperties": False,
}
PRODUCTION_OUTPUTS_QUERY_INPUT_SCHEMA = {
    "type": "object",
    "properties": {
        "publish_date": {"type": "string", "pattern": r"^\d{4}-\d{2}-\d{2}$"},
    },
    "required": ["publish_date"],
    "additionalProperties": False,
}
FINANCE_SAVE_DRAFT_INPUT_SCHEMA = {
    "type": "object",
    "properties": {
        "topic": {"type": "string", "minLength": 1},
        "article": {
            "type": "string",
            "minLength": 1,
            "description": "财经正文；三类必做改动（品牌替换、连载指涉改写、错别字修正）之外允许措辞级改写，但大结构、观点顺序与信息量必须与原稿一致，每行不超过 36 字",
        },
        "title": {"type": "string", "minLength": 12, "maxLength": 26},
        "short_title": {"type": "string", "minLength": 6, "maxLength": 16},
        "hashtags": {
            "type": "array",
            "minItems": 4,
            "maxItems": 4,
            "uniqueItems": True,
            "items": {"type": "string", "minLength": 1},
        },
        "draft_path": {"type": "string", "description": "修改已生成稿件时传入原 draft_path；话题不得改变"},
        "cover_lines": {
            "type": "array",
            "minItems": 1,
            "maxItems": 3,
            "items": {"type": "string", "minLength": 1},
            "description": "封面标题行，由 Agent 按语义拆成 1 至 3 行；工具不自动折行",
        },
        "cover_highlights": {
            "type": "array",
            "minItems": 1,
            "uniqueItems": True,
            "items": {"type": "string", "minLength": 1},
            "description": "长标题中需要标成金黄色的重点词；每项必须原样出现在 title 中",
        },
        "source_aweme_id": {
            "type": "string",
            "pattern": r"^\d+$",
            "description": "finance_get_source_script 返回的抖音作品 ID",
        },
        "source_reservation_token": {
            "type": "string",
            "minLength": 1,
            "description": "finance_get_source_script 返回的占用令牌",
        },
        "source_hook": {
            "type": "string",
            "minLength": 1,
            "description": "原稿开头黄金钩子完成品牌替换后的版本；钩子不做措辞改写，正文开头忽略空白后必须原样匹配；可按语义换行，每行不超过36字",
        },
        "publish_date": {
            "type": "string",
            "pattern": r"^\d{4}-\d{2}-\d{2}$",
            "description": "北京时间计划发布日期；run_id 将生成为 run-YYYYMMDD",
        },
    },
    "required": [
        "topic",
        "article",
        "title",
        "short_title",
        "hashtags",
        "cover_lines",
        "cover_highlights",
        "source_aweme_id",
        "source_reservation_token",
        "source_hook",
        "publish_date",
    ],
    "additionalProperties": False,
}

FINANCE_SOURCE_SCRIPT_OUTPUT_SCHEMA = {
    "type": "object",
    "properties": {
        "source": {"type": "object"},
        "reservation": {"type": "object"},
        "reservation_minutes": {"type": "integer", "minimum": 1},
    },
    "required": ["source", "reservation", "reservation_minutes"],
    "additionalProperties": False,
}
FINANCE_SOURCE_STATS_OUTPUT_SCHEMA = {
    "type": "object",
    "properties": {
        "collection_code": {"type": "string", "const": "finance"},
        "workflow": {"type": "string", "const": "finance"},
        "reservation_minutes": {"type": "integer", "minimum": 1},
        "total_count": {"type": "integer", "minimum": 0},
        "available_count": {"type": "integer", "minimum": 0},
        "reserved_count": {"type": "integer", "minimum": 0},
        "used_count": {"type": "integer", "minimum": 0},
        "checked_at": {"type": "string"},
    },
    "required": [
        "collection_code",
        "workflow",
        "reservation_minutes",
        "total_count",
        "available_count",
        "reserved_count",
        "used_count",
        "checked_at",
    ],
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
        "poll_tool": {"type": "string", "const": "finance_poll_task"},
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
