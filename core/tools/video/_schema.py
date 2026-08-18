"""generate_video 的真实入参和返回合同。

这不是 MCP 注册表。失败时抛出 VideoToolError 子类，不返回 error 对象。
"""

from __future__ import annotations

from ._constants import SUPPORTED_SUBTITLE_LANGUAGES

__all__ = [
    "MOTION_SCHEMA",
    "SHOT_ITEM_SCHEMA",
    "GENERATE_VIDEO_INPUT_SCHEMA",
    "GENERATE_VIDEO_OUTPUT_SCHEMA",
]

MOTION_SCHEMA = {
    "type": "object",
    "description": "可选确定性缩放/平移动效；不传则为静态画面",
    "properties": {
        "zoom_from": {"type": "number", "minimum": 1.0, "maximum": 2.0},
        "zoom_to": {"type": "number", "minimum": 1.0, "maximum": 2.0},
        "pan_from_x": {"type": "number", "minimum": 0.0, "maximum": 1.0},
        "pan_from_y": {"type": "number", "minimum": 0.0, "maximum": 1.0},
        "pan_to_x": {"type": "number", "minimum": 0.0, "maximum": 1.0},
        "pan_to_y": {"type": "number", "minimum": 0.0, "maximum": 1.0},
    },
    "additionalProperties": False,
}

SHOT_ITEM_SCHEMA = {
    "type": "object",
    "description": "一个镜头。传入 segment_path 则直接使用该 MP4；否则按图片渲染，且必须有 audio_path 或 duration。",
    "properties": {
        "id": {"type": "string", "minLength": 1, "description": "镜头唯一 id"},
        "segment_path": {"type": "string", "description": "已渲染好的镜头 MP4；传入后忽略本镜头的图片/语音/字幕/动效"},
        "image_path": {"type": "string", "description": "静态图片路径"},
        "duration": {"type": "number", "exclusiveMinimum": 0, "description": "无语音时的镜头时长（秒）"},
        "audio_path": {"type": "string", "description": "语音路径；传入后以语音真实时长为准，忽略 duration"},
        "audio_start": {"type": "number", "minimum": 0, "description": "从完整语音中截取的起点秒数"},
        "audio_end": {"type": "number", "exclusiveMinimum": 0, "description": "从完整语音中截取的终点秒数"},
        "subtitle": {"type": "string", "description": "烧录字幕文本；不传则无字幕"},
        "subtitle_language": {
            "type": "string",
            "enum": SUPPORTED_SUBTITLE_LANGUAGES,
            "default": "zh",
            "description": "字幕语言；不传为 zh",
        },
        "motion": MOTION_SCHEMA,
    },
    "required": ["id"],
    "anyOf": [
        {"required": ["segment_path"]},
        {
            "required": ["image_path"],
            "anyOf": [{"required": ["audio_path"]}, {"required": ["duration"]}],
        },
    ],
    "additionalProperties": False,
}

GENERATE_VIDEO_INPUT_SCHEMA = {
    "type": "object",
    "description": "generate_video(...) 的关键字参数合同",
    "properties": {
        "shots": {
            "type": "array",
            "minItems": 1,
            "items": SHOT_ITEM_SCHEMA,
            "description": "按播放顺序的镜头列表；可混用预渲染片段和待渲染镜头",
        },
        "size": {
            "type": "string",
            "pattern": r"^\s*\d+\s*[xX×]\s*\d+\s*$",
            "description": "全部镜头统一输出尺寸，例如 1920x1080",
        },
        "cache_dir": {"type": "string", "description": "镜头缓存和中间成片目录"},
        "output_dir": {"type": "string", "description": "成品输出目录"},
        "title": {"type": "string", "minLength": 1, "description": "成品文件名使用该标题"},
        "cover_path": {"type": "string", "description": "封面图路径；不传或空则不加封面"},
        "bgm_path": {"type": "string", "description": "BGM 路径；不传或空则不混音"},
        "force_shot_ids": {
            "type": "array",
            "items": {"type": "string"},
            "uniqueItems": True,
            "description": "强制重做的镜头 id；必须是 shots 里已有的 id。预渲染镜头仍使用传入的 segment_path",
        },
        "gain": {"type": "number", "minimum": 0, "description": "仅混 BGM 时生效；不传用 BGM 能力默认值"},
        "mix_gain": {"type": "number", "minimum": 0, "description": "仅混 BGM 时生效；不传用 BGM 能力默认值"},
        "fade_in": {"type": "number", "minimum": 0, "description": "仅混 BGM 时生效；不传用 BGM 能力默认值"},
        "fade_out": {"type": "number", "minimum": 0, "description": "仅混 BGM 时生效；不传用 BGM 能力默认值"},
    },
    "required": ["shots", "size", "cache_dir", "output_dir", "title"],
    "additionalProperties": False,
}

GENERATE_VIDEO_OUTPUT_SCHEMA = {
    "type": "object",
    "description": "generate_video 成功时返回的 dict",
    "properties": {
        "output_path": {"type": "string", "description": "成品 MP4 路径，文件名来自 title"},
        "duration": {"type": "number", "description": "成品时长（秒）"},
        "shot_count": {"type": "integer", "description": "镜头总数"},
        "cache_hits": {"type": "integer", "description": "命中镜头缓存、因此未重渲染的数量"},
        "rendered_shots": {"type": "integer", "description": "本次实际渲染的镜头数量，不含预渲染片段"},
        "shots": {
            "type": "array",
            "items": {
                "type": "object",
                "properties": {
                    "id": {"type": "string"},
                    "cache_hit": {"type": "boolean", "description": "是否命中镜头缓存"},
                    "pre_rendered": {"type": "boolean", "description": "是否使用调用方传入的 segment_path"},
                    "segment_path": {"type": "string", "description": "该镜头实际使用的 MP4 路径"},
                    "duration": {"type": "number", "description": "该镜头时长（秒）"},
                },
                "required": ["id", "cache_hit", "pre_rendered", "segment_path", "duration"],
                "additionalProperties": False,
            },
        },
        "has_cover": {"type": "boolean", "description": "本次是否加了封面"},
        "has_bgm": {"type": "boolean", "description": "本次是否混了 BGM"},
        "bgm_path": {"type": ["string", "null"], "description": "实际混入的 BGM 路径；未混则为 null"},
        "gain": {"type": ["number", "null"], "description": "未混 BGM 时为 null"},
        "mix_gain": {"type": ["number", "null"], "description": "未混 BGM 时为 null"},
        "fade_in": {"type": ["number", "null"], "description": "未混 BGM 时为 null"},
        "fade_out": {"type": ["number", "null"], "description": "未混 BGM 时为 null"},
    },
    "required": [
        "output_path", "duration", "shot_count", "cache_hits", "rendered_shots", "shots",
        "has_cover", "has_bgm", "bgm_path", "gain", "mix_gain", "fade_in", "fade_out",
    ],
    "additionalProperties": False,
}
