"""生图任务的真实入参和返回合同。

公开入口分三类，互不耦合：
- 宿主 Agent：prepare_agent_image_tasks / save_agent_image_tasks / submit_agent_image_tasks
- 方舟：generate_ark_image
- 本地选：list_local_images
宿主失败后是否改走方舟，由业务 MCP（如语言学习）决定，不放在 image 内。
"""

from __future__ import annotations

from ._constants import SUPPORTED_STYLE_IDS

IMAGE_GENERATION_ERROR_SCHEMA = {
    "type": "object",
    "properties": {
        "error": {
            "type": "object",
            "properties": {
                "code": {
                    "type": "string",
                    "enum": [
                        "INVALID_PARAMETER", "STYLE_NOT_FOUND", "REFERENCE_IMAGE_ERROR",
                        "AI_CONFIGURATION_ERROR", "AI_GENERATION_FAILED", "AGENT_IMAGE_TASK_ERROR",
                        "IMAGE_LIBRARY_DATA_ERROR", "IMAGE_LIBRARY_EMPTY",
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

PREPARE_AGENT_IMAGE_TASKS_INPUT_SCHEMA = {
    "type": "object",
    "properties": {
        "tasks": {
            "type": "array",
            "minItems": 1,
            "items": {
                "type": "object",
                "properties": {
                    "image_id": {"type": "string", "pattern": r"^[A-Za-z0-9_-]+$"},
                    "kind": {"type": "string"},
                    "prompt": {"type": "string", "minLength": 1},
                },
                "required": ["image_id", "prompt"],
                "additionalProperties": False,
            },
        },
        "style": {"type": "string", "enum": SUPPORTED_STYLE_IDS, "description": "可选；不传则不套画风、不附加画风参考图"},
        "radio": {"type": "string"},
        "size": {"type": "string"},
        "cache_dir": {"type": "string", "minLength": 1},
        "additional_reference_image_paths": {
            "type": "array",
            "items": {"type": "string", "minLength": 1},
            "uniqueItems": True,
            "description": "可选；除画风参考图外，由业务工作流补充的人物、服饰或场景参考图",
        },
        "context_path": {"type": "string", "minLength": 1},
        "force_image_ids": {"type": "array", "items": {"type": "string"}, "uniqueItems": True},
        "force_images": {"type": "boolean", "default": False},
        "metadata": {"type": "object"},
    },
    "required": ["tasks", "radio", "size", "cache_dir"],
    "additionalProperties": False,
}

SAVE_AGENT_IMAGE_TASKS_INPUT_SCHEMA = {
    "type": "object",
    "properties": {
        "context_path": {"type": "string", "minLength": 1},
        "images": {
            "type": "array",
            "minItems": 1,
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
    },
    "required": ["context_path", "images"],
    "additionalProperties": False,
}

SUBMIT_AGENT_IMAGE_TASKS_INPUT_SCHEMA = {
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
        "manifest_path": {"type": "string", "minLength": 1},
    },
    "required": ["context_path", "images"],
    "additionalProperties": False,
}

GENERATE_ARK_IMAGE_INPUT_SCHEMA = {
    "type": "object",
    "properties": {
        "prompt": {"type": "string", "minLength": 1},
        "output_path": {"type": "string", "minLength": 1},
        "size": {"type": "string"},
        "reference_image_paths": {"type": "array", "items": {"type": "string"}},
        "cache_signature": {"type": "string"},
    },
    "required": ["prompt", "output_path", "size"],
    "additionalProperties": False,
}

LIST_LOCAL_IMAGES_INPUT_SCHEMA = {
    "type": "object",
    "properties": {
        "line": {"type": "string", "minLength": 1, "description": "业务线 id，如 finance"},
    },
    "required": ["line"],
    "additionalProperties": False,
}

LIST_LOCAL_IMAGES_OUTPUT_SCHEMA = {
    "type": "array",
    "items": {
        "type": "object",
        "properties": {
            "id": {"type": "integer"},
            "caption": {"type": "string"},
            "image_path": {"type": "string"},
        },
        "required": ["id", "caption", "image_path"],
        "additionalProperties": False,
    },
}
