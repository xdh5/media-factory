"""生图任务的真实入参和返回合同。

这不是 MCP 注册表。失败时抛出 ImageGenerationError 子类，不返回 error 对象。
公开入口仍是 prepare_agent_image_tasks 与 submit_agent_image_tasks 两步，因为中间必须由 Agent 生图。
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
        "exact_size": {
            "type": "boolean",
            "default": True,
            "description": "为 false 时只要宽高比正确就会缩放到 size，不要求像素精确匹配",
        },
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
        "manifest_path": {"type": "string", "minLength": 1},
    },
    "required": ["context_path", "images"],
    "additionalProperties": False,
}
