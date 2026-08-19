"""parse_link 与 transcribe_media 的真实入参和返回合同。"""

from __future__ import annotations

from ._constants import SUPPORTED_LANGUAGES

PARSE_LINK_INPUT_SCHEMA = {
    "type": "object",
    "properties": {
        "share_text": {
            "type": "string",
            "minLength": 1,
            "description": "平台分享口令、短链或完整视频链接",
        },
    },
    "required": ["share_text"],
    "additionalProperties": False,
}

PARSE_LINK_OUTPUT_SCHEMA = {
    "type": "object",
    "properties": {
        "video_id": {"type": "string"},
        "platform": {"type": "string"},
        "title": {"type": ["string", "null"]},
        "video_url": {"type": "string", "description": "可直接下载或交给转写的真实视频地址"},
        "cover_url": {"type": ["string", "null"]},
        "audio_url": {"type": "string", "description": "仅哔哩哔哩可能返回"},
    },
    "required": ["video_id", "platform", "title", "video_url", "cover_url"],
    "additionalProperties": False,
}

TRANSCRIBE_MEDIA_INPUT_SCHEMA = {
    "type": "object",
    "properties": {
        "media_path": {
            "type": "string",
            "minLength": 1,
            "description": "本地音视频路径，或 parse_link 返回的 video_url",
        },
        "language": {
            "type": "string",
            "enum": list(SUPPORTED_LANGUAGES),
            "default": "zh",
            "description": "识别语言；不传为 zh。只返回 Whisper 原文，不做错别字校对",
        },
        "filename": {"type": "string", "description": "可选展示文件名"},
    },
    "required": ["media_path"],
    "additionalProperties": False,
}

TRANSCRIBE_MEDIA_OUTPUT_SCHEMA = {
    "type": "object",
    "properties": {
        "filename": {"type": "string"},
        "language": {"type": "string"},
        "text": {"type": "string", "description": "Whisper 原文，未经错别字校对"},
        "segments": {
            "type": "array",
            "items": {
                "type": "object",
                "properties": {
                    "start": {"type": ["number", "null"]},
                    "end": {"type": ["number", "null"]},
                    "text": {"type": "string"},
                },
                "required": ["start", "end", "text"],
                "additionalProperties": False,
            },
        },
    },
    "required": ["filename", "language", "text", "segments"],
    "additionalProperties": False,
}

GET_JOB_INPUT_SCHEMA = {
    "type": "object",
    "properties": {
        "job_id": {"type": "string", "pattern": r"^job-[0-9a-f]{32}$"},
        "database_path": {"type": "string"},
    },
    "required": ["job_id"],
    "additionalProperties": False,
}

WAIT_TASK_INPUT_SCHEMA = {
    "type": "object",
    "properties": {
        "job_id": {"type": "string", "pattern": r"^job-[0-9a-f]{32}$"},
        "database_path": {"type": "string"},
        "timeout": {
            "type": "number",
            "exclusiveMinimum": 0,
            "maximum": 180,
            "description": "单次最多阻塞秒数，默认 180；超时仍 queued/running 则再调一次",
        },
    },
    "required": ["job_id"],
    "additionalProperties": False,
}
