"""download 的真实入参和返回合同。"""

from __future__ import annotations

DOWNLOAD_INPUT_SCHEMA = {
    "type": "object",
    "description": "从分享口令或链接解析并下载视频到本地",
    "properties": {
        "share_text": {
            "type": "string",
            "minLength": 1,
            "description": "平台分享口令、短链或完整视频链接",
        },
        "output_path": {
            "type": "string",
            "description": "可选本地保存路径，须为 .mp4；不传则写入 data/download/videos/",
        },
    },
    "required": ["share_text"],
    "additionalProperties": False,
}

DOWNLOAD_OUTPUT_SCHEMA = {
    "type": "object",
    "properties": {
        "video_id": {"type": "string"},
        "platform": {"type": "string"},
        "title": {"type": ["string", "null"]},
        "video_path": {"type": "string", "description": "已下载的本地视频路径"},
        "cover_url": {"type": ["string", "null"]},
    },
    "required": ["video_id", "platform", "title", "video_path", "cover_url"],
    "additionalProperties": False,
}
