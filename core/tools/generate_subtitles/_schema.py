"""generate_subtitles 的真实入参和返回合同。"""

from __future__ import annotations

from ._constants import (
    SUPPORTED_SUBTITLE_ALIGNMENTS,
    SUPPORTED_SUBTITLE_ANIMATIONS,
    SUPPORTED_SUBTITLE_LANGUAGES,
    SUPPORTED_SUBTITLE_PRESETS,
)

__all__ = [
    "GENERATE_SUBTITLES_INPUT_SCHEMA",
    "GENERATE_SUBTITLES_OUTPUT_SCHEMA",
    "SUBTITLE_POSITION_SCHEMA",
    "SUBTITLE_STYLE_SCHEMA",
    "SUBTITLE_WORD_SCHEMA",
]

_COLOR_SCHEMA = {
    "type": "string",
    "minLength": 1,
    "description": "颜色：#RRGGBB、RRGGBB 或 ASS &H 格式",
}

SUBTITLE_STYLE_SCHEMA = {
    "type": "object",
    "description": (
        "字幕视觉样式；未传字段沿用语言默认。preset 可一键套用爆款样式："
        f"{SUPPORTED_SUBTITLE_PRESETS}（会启用逐词动画，可再用显式字段覆盖）"
    ),
    "properties": {
        "preset": {
            "type": "string",
            "enum": SUPPORTED_SUBTITLE_PRESETS,
            "description": "爆款字幕预设（移植自 ai-video-captions）",
        },
        "font": {"type": "string", "minLength": 1},
        "font_size": {"type": "number", "minimum": 8, "description": "字号（像素），默认 100"},
        "font_size_ratio": {
            "type": "number",
            "minimum": 0,
            "maximum": 1,
            "description": "相对画布高度的字号比例；font_size 优先",
        },
        "primary_color": _COLOR_SCHEMA,
        "secondary_color": _COLOR_SCHEMA,
        "outline_color": _COLOR_SCHEMA,
        "back_color": _COLOR_SCHEMA,
        "highlight_color": {
            "type": "string",
            "description": "逐词动画高亮色（当前词/扫过颜色）",
        },
        "animation": {
            "type": "string",
            "enum": SUPPORTED_SUBTITLE_ANIMATIONS,
            "description": (
                "逐词动画：highlight=重点词换色 / karaoke=颜色从左到右扫过 / "
                "scale=当前词放大 / bounce=当前词弹跳；设置后 cue 按词出事件"
            ),
        },
        "uppercase": {
            "type": "boolean",
            "description": "拉丁字符转大写（中文无副作用）",
        },
        "letter_spacing": {
            "type": "number",
            "minimum": 0,
            "maximum": 50,
            "description": "字符间距（ASS \\fsp，像素）",
        },
        "outline": {"type": "number", "minimum": 0, "description": "描边宽度（像素）"},
        "outline_ratio": {"type": "number", "minimum": 0, "maximum": 1},
        "shadow": {"type": "number", "minimum": 0, "description": "阴影深度（像素）"},
        "shadow_ratio": {"type": "number", "minimum": 0, "maximum": 1},
        "bold": {"type": "boolean"},
        "italic": {"type": "boolean"},
        "max_lines": {"type": "integer", "minimum": 1, "maximum": 4, "default": 2},
        "canvas_width_ratio": {
            "type": "number",
            "minimum": 0.1,
            "maximum": 1,
            "description": "换行可用宽度占画布比例",
        },
    },
    "additionalProperties": False,
}

SUBTITLE_POSITION_SCHEMA = {
    "type": "object",
    "description": "字幕位置；未传字段沿用语言默认",
    "properties": {
        "alignment": {
            "type": "integer",
            "enum": SUPPORTED_SUBTITLE_ALIGNMENTS,
            "description": "ASS 对齐：1 左下（边距框内左对齐换行）… 2 中下（每行单独居中）",
        },
        "margin_left": {"type": "number", "minimum": 0},
        "margin_right": {"type": "number", "minimum": 0},
        "margin_vertical": {"type": "number", "minimum": 0, "description": "距底/顶边距（像素）"},
        "margin_left_ratio": {"type": "number", "minimum": 0, "maximum": 1},
        "margin_right_ratio": {"type": "number", "minimum": 0, "maximum": 1},
        "margin_vertical_ratio": {"type": "number", "minimum": 0, "maximum": 1},
        "x": {"type": "number", "minimum": 0, "description": "绝对坐标 x，须与 y 同传"},
        "y": {"type": "number", "minimum": 0, "description": "绝对坐标 y，须与 x 同传"},
    },
    "additionalProperties": False,
}

SUBTITLE_TEXT_SPAN_SCHEMA = {
    "type": "object",
    "description": "句内分段；可对某几个字单独设 style",
    "properties": {
        "text": {"type": "string", "minLength": 1},
        "style": SUBTITLE_STYLE_SCHEMA,
    },
    "required": ["text"],
    "additionalProperties": False,
}

SUBTITLE_WORD_SCHEMA = {
    "type": "object",
    "description": "词级时间；时间为整片绝对时间或相对 cue 起点",
    "properties": {
        "text": {"type": "string", "minLength": 1},
        "start": {"type": "number", "minimum": 0, "description": "词开始时间（秒）"},
        "end": {"type": "number", "exclusiveMinimum": 0, "description": "词结束时间（秒）"},
    },
    "required": ["text", "start", "end"],
    "additionalProperties": False,
}

_CUE_SCHEMA = {
    "type": "object",
    "properties": {
        "start": {"type": "number", "minimum": 0},
        "end": {"type": "number", "exclusiveMinimum": 0},
        "text": {
            "oneOf": [
                {"type": "string", "minLength": 1},
                {"type": "array", "minItems": 1, "items": SUBTITLE_TEXT_SPAN_SCHEMA},
            ],
            "description": (
                "整句字符串，或分段数组以句内混排样式；"
                "启用逐词动画（preset/animation）时须为整句字符串"
            ),
        },
        "words": {
            "type": "array",
            "minItems": 1,
            "items": SUBTITLE_WORD_SCHEMA,
            "description": (
                "可选词级时间；缺省时按中文逐字/英文分词在 cue 区间内均匀分布"
            ),
        },
        "language": {
            "type": "string",
            "enum": list(SUPPORTED_SUBTITLE_LANGUAGES),
            "default": "zh",
        },
        "style": SUBTITLE_STYLE_SCHEMA,
        "position": SUBTITLE_POSITION_SCHEMA,
    },
    "required": ["start", "end", "text"],
    "additionalProperties": False,
}

GENERATE_SUBTITLES_INPUT_SCHEMA = {
    "type": "object",
    "description": "generate_subtitles(...) 的关键字参数合同",
    "properties": {
        "cues": {"type": "array", "minItems": 1, "items": _CUE_SCHEMA},
        "output_path": {"type": "string", "minLength": 1, "description": "产出的 .ass 路径"},
        "width": {"type": "integer", "minimum": 2, "description": "画布宽，须为偶数"},
        "height": {"type": "integer", "minimum": 2, "description": "画布高，须为偶数"},
        "style": SUBTITLE_STYLE_SCHEMA,
        "position": SUBTITLE_POSITION_SCHEMA,
    },
    "required": ["cues", "output_path", "width", "height"],
    "additionalProperties": False,
}

GENERATE_SUBTITLES_OUTPUT_SCHEMA = {
    "type": "object",
    "properties": {
        "output_path": {"type": "string"},
        "fontsdir": {"type": "string"},
        "width": {"type": "integer"},
        "height": {"type": "integer"},
    },
    "required": ["output_path", "fontsdir", "width", "height"],
    "additionalProperties": False,
}
