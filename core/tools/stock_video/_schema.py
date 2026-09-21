"""正版视频素材工具输入输出结构。"""

STOCK_VIDEO_CANDIDATE_SCHEMA = {
    "type": "object",
    "properties": {
        "provider": {"type": "string", "enum": ["pexels", "pixabay", "coverr"]},
        "id": {"type": "string"},
        "title": {"type": "string"},
        "page_url": {"type": "string"},
        "download_url": {"type": "string"},
        "preview_url": {"type": "string"},
        "duration": {"type": "number"},
        "width": {"type": "integer"},
        "height": {"type": "integer"},
        "creator": {"type": "string"},
        "attribution": {"type": "string"},
        "attribution_url": {"type": "string"},
    },
    "required": [
        "provider", "id", "title", "page_url", "download_url", "preview_url",
        "duration", "width", "height", "creator", "attribution", "attribution_url",
    ],
    "additionalProperties": False,
}

SEARCH_STOCK_VIDEOS_INPUT_SCHEMA = {
    "type": "object",
    "properties": {
        "query": {"type": "string", "minLength": 1, "maxLength": 100},
        "orientation": {"type": "string", "enum": ["landscape", "portrait", "square"]},
        "per_provider": {"type": "integer", "minimum": 1, "maximum": 40},
        "providers": {
            "type": "array",
            "minItems": 1,
            "uniqueItems": True,
            "items": {"type": "string", "enum": ["pexels", "pixabay", "coverr"]},
        },
    },
    "required": ["query"],
    "additionalProperties": False,
}

DOWNLOAD_STOCK_VIDEO_INPUT_SCHEMA = {
    "type": "object",
    "properties": {
        "candidate": STOCK_VIDEO_CANDIDATE_SCHEMA,
        "output_path": {"type": "string", "minLength": 1},
    },
    "required": ["candidate", "output_path"],
    "additionalProperties": False,
}

PREPARE_STOCK_CLIP_INPUT_SCHEMA = {
    "type": "object",
    "properties": {
        "source_path": {"type": "string", "minLength": 1},
        "output_path": {"type": "string", "minLength": 1},
        "duration": {"type": "number", "exclusiveMinimum": 0},
        "size": {"type": "string", "pattern": r"^\d+x\d+$"},
        "frame_path": {"type": ["string", "null"]},
    },
    "required": ["source_path", "output_path", "duration"],
    "additionalProperties": False,
}
