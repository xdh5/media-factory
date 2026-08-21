"""generate_bgm 的真实入参与返回合同。"""

from __future__ import annotations

GENERATE_BGM_INPUT_SCHEMA = {
    "type": "object",
    "description": "按目标时长循环或裁剪源曲，产出固定音量的 BGM 音轨",
    "properties": {
        "bgm_path": {"type": "string", "minLength": 1, "description": "源曲路径"},
        "output_path": {"type": "string", "minLength": 1, "description": "产出的 .m4a 路径"},
        "duration": {"type": "number", "exclusiveMinimum": 0, "description": "目标时长（秒），通常等于成片时长"},
        "fade_in": {"type": "number", "minimum": 0, "description": "可选淡入秒数；不传用默认 1 秒，传 0 关闭"},
        "fade_out": {"type": "number", "minimum": 0, "description": "可选淡出秒数；不传用默认 2 秒，传 0 关闭"},
    },
    "required": ["bgm_path", "output_path", "duration"],
    "additionalProperties": False,
}

GENERATE_BGM_OUTPUT_SCHEMA = {
    "type": "object",
    "properties": {
        "output_path": {"type": "string"},
        "duration": {"type": "number"},
        "bgm_path": {"type": "string"},
        "gain": {"type": "number"},
        "looped": {"type": "boolean"},
        "fade_in": {"type": "number"},
        "fade_out": {"type": "number"},
    },
    "required": ["output_path", "duration", "bgm_path", "gain", "looped", "fade_in", "fade_out"],
    "additionalProperties": False,
}
