"""select_bgm 的输入输出 JSON Schema。

供 agent 框架注册工具时使用（如 MCP tool 的 inputSchema）。
"""

from __future__ import annotations

from ._constants import (
    MOOD_DESCRIPTIONS,
    SUPPORTED_MOODS,
)

__all__ = [
    "SELECT_BGM_INPUT_SCHEMA",
    "SELECT_BGM_OUTPUT_SCHEMA",
    "SELECT_BGM_ERROR_SCHEMA",
]

# 输入参数 schema
SELECT_BGM_INPUT_SCHEMA = {
    "type": "object",
    "properties": {
        "mood": {
            "type": "string",
            "description": (
                "需要匹配的音乐情绪，采用 GEMS-9 九维模型。可用枚举："
                + "、".join(f"{key}（{label}）" for key, label in MOOD_DESCRIPTIONS.items())
                + "。请根据受众实际感受选择，不要把视频用途当作情绪。"
            ),
            "enum": SUPPORTED_MOODS,
        },
        "id": {
            "type": "string",
            "description": "BGM 唯一 ID。传入时精确选择该曲目，不能与 mood 同时传入。",
        },
    },
    "oneOf": [
        {"required": ["mood"], "not": {"required": ["id"]}},
        {"required": ["id"], "not": {"required": ["mood"]}},
    ],
}

# 成功输出 schema（select_bgm 的返回值）
SELECT_BGM_OUTPUT_SCHEMA = {
    "type": "object",
    "properties": {
        "id": {
            "type": "string",
            "description": "BGM 唯一 ID，后续渲染/记录时直接用这个引用",
        },
        "name": {
            "type": "string",
            "description": "人类可读的 BGM 名称（含作者/来源），用于 UI 展示",
        },
        "path": {
            "type": "string",
            "description": "BGM mp3 的绝对路径，直接交给 ffmpeg/合成阶段读取",
        },
        "matched_mood": {
            "type": ["string", "null"],
            "description": "按 mood 匹配时为入参 mood；按 id 精确选择时为 null",
        },
    },
    "required": ["id", "name", "path", "matched_mood"],
}

# 错误输出 schema（BGMSelectError.to_dict() 的结构）
SELECT_BGM_ERROR_SCHEMA = {
    "type": "object",
    "properties": {
        "error": {
            "type": "object",
            "properties": {
                "code": {
                    "type": "string",
                    "description": "错误码",
                    "enum": [
                        "INVALID_PARAMETER",  # 参数非法，details.parameter 指出问题参数
                        "BGM_NOT_FOUND",      # mood 没有对应 BGM，
                                              # details.supported_moods /
                                              # available_bgm 给 Agent 修正方向
                        "BGM_ID_NOT_FOUND",   # id 不存在，details.available_ids 列出可用 ID
                        "BGM_FILE_NOT_FOUND", # ID 存在，但对应静态音频文件缺失
                    ],
                },
                "message": {
                    "type": "string",
                    "description": "人类可读错误信息，已包含可用枚举提示",
                },
                "details": {
                    "type": "object",
                    "description": "附加信息（parameter、requested、supported_moods 等）；BGM_NOT_FOUND 时含可用曲库概览",
                },
            },
            "required": ["code", "message", "details"],
        },
    },
    "required": ["error"],
}
