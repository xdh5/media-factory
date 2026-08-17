"""生图功能的输入输出 JSON Schema。"""

from __future__ import annotations

from ._constants import SUPPORTED_STYLE_IDS

GENERATE_IMAGE_INPUT_SCHEMA = {
    "type": "object",
    "properties": {
        "prompt": {"type": "string", "minLength": 1, "description": "需要生成的画面提示词"},
        "style": {
            "type": "string",
            "enum": SUPPORTED_STYLE_IDS,
            "description": "画风：painterly 油画、realistic 写实、paper 折纸",
        },
        "radio": {
            "type": "string",
            "pattern": r"^\s*\d+\s*:\s*\d+\s*$",
            "description": "画面宽高比，例如 16:9",
        },
        "size": {
            "type": "string",
            "pattern": r"^\s*\d+\s*[xX×]\s*\d+\s*$",
            "description": "输出像素尺寸，例如 2560x1440",
        },
        "force_regenerate": {
            "type": "boolean",
            "default": False,
            "description": "为 true 时忽略已有缓存并重新生图",
        },
        "cache_dir": {
            "type": "string",
            "minLength": 1,
            "description": "可选；指定生图缓存目录，工作流应传入自己的统一缓存目录",
        },
    },
    "required": ["prompt", "style", "radio", "size"],
    "additionalProperties": False,
}

GENERATE_IMAGE_OUTPUT_SCHEMA = {
    "type": "object",
    "properties": {
        "output_path": {"type": "string"},
        "provider": {"type": "string", "enum": ["current_agent", "volc_ark"]},
        "model": {"type": "string"},
        "style": {"type": "string", "enum": SUPPORTED_STYLE_IDS},
        "radio": {"type": "string"},
        "size": {"type": "string"},
        "agent_attempts": {"type": "integer", "minimum": 0, "maximum": 3},
        "cache_hit": {"type": "boolean"},
        "cache_key": {"type": "string"},
    },
    "required": [
        "output_path", "provider", "model", "style", "radio", "size",
        "agent_attempts", "cache_hit", "cache_key",
    ],
    "additionalProperties": False,
}

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
                        "AGENT_GENERATION_FAILED", "AI_CONFIGURATION_ERROR", "AI_GENERATION_FAILED",
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
