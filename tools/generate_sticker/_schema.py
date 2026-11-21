"""generate_sticker 的真实入参和返回合同。"""

from __future__ import annotations

from ._constants import SUPPORTED_STICKERS

__all__ = [
    "GENERATE_STICKER_INPUT_SCHEMA",
    "GENERATE_STICKER_OUTPUT_SCHEMA",
]

GENERATE_STICKER_INPUT_SCHEMA = {
    "type": "object",
    "description": "generate_sticker(...) 的关键字参数合同；只产出贴图素材，不烧进视频",
    "properties": {
        "sticker": {
            "type": "string",
            "enum": list(SUPPORTED_STICKERS),
            "description": "贴图标识。rec 为可选素材之一（红圆闪烁 + REC 字），不是唯一贴图",
        },
        "output_path": {
            "type": "string",
            "minLength": 1,
            "description": "素材路径。动态贴图（如 rec）必须使用 .mov",
        },
        "width": {"type": "integer", "minimum": 2, "description": "目标画布宽，须为偶数，用于按高度缩放"},
        "height": {"type": "integer", "minimum": 2, "description": "目标画布高，须为偶数"},
        "duration": {
            "type": ["number", "null"],
            "exclusiveMinimum": 0,
            "description": "countdown 贴图必传，控制 3、2、1 扫盘动画的总时长",
        },
    },
    "required": ["sticker", "output_path", "width", "height"],
    "additionalProperties": False,
}

GENERATE_STICKER_OUTPUT_SCHEMA = {
    "type": "object",
    "properties": {
        "output_path": {"type": "string"},
        "sticker": {"type": "string"},
        "width": {"type": "integer", "description": "素材画面宽"},
        "height": {"type": "integer", "description": "素材画面高"},
        "x": {"type": "integer", "description": "叠到画布上的左上角 x"},
        "y": {"type": "integer", "description": "叠到画布上的左上角 y"},
        "loop": {"type": "boolean", "description": "是否按素材时长循环，供 overlay 使用"},
        "duration": {"type": "number", "description": "单次贴图素材时长"},
    },
    "required": ["output_path", "sticker", "width", "height", "x", "y", "loop"],
    "additionalProperties": False,
}
