"""图库挑选的真实入参和返回合同。"""

from __future__ import annotations

PICK_FOR_SHOTS_INPUT_SCHEMA = {
    "type": "object",
    "properties": {
        "line": {"type": "string", "minLength": 1, "description": "业务线 id，如 finance"},
        "shots": {
            "type": "array",
            "minItems": 1,
            "items": {
                "type": "object",
                "properties": {
                    "image_id": {"type": "string", "minLength": 1},
                    "query": {"type": "string", "description": "分镜画面描述与台词，用于匹配 tags/concepts"},
                },
                "required": ["image_id", "query"],
                "additionalProperties": False,
            },
        },
        "exclude_library_ids": {
            "type": "array",
            "items": {"type": "integer"},
            "uniqueItems": True,
            "description": "本次已占用的图库 id，不得再抽",
        },
        "database_path": {"type": "string"},
    },
    "required": ["line", "shots"],
    "additionalProperties": False,
}

LIBRARY_PICK_SCHEMA = {
    "type": "object",
    "properties": {
        "image_id": {"type": "string"},
        "library_id": {"type": "integer"},
        "caption": {"type": "string"},
        "tags": {"type": "array", "items": {"type": "string"}},
        "concepts": {"type": "array", "items": {"type": "string"}},
        "source_path": {"type": "string"},
        "score": {"type": "integer"},
        "window_count": {"type": "integer"},
        "idle_days": {"type": "integer"},
    },
    "required": ["image_id", "library_id", "caption", "tags", "concepts", "source_path", "score"],
}
