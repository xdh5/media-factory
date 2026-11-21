"""数据库接口数据合同。"""

LANGUAGE_LEARNING_PACK_SCHEMA = {
    "type": "object",
    "properties": {
        "pack_id": {"type": "string", "minLength": 1},
        "topic": {"type": "string", "pattern": "^[A-Za-z]+$"},
        "words": {"type": "object"},
        "image_urls": {"type": "array", "minItems": 10, "maxItems": 10, "items": {"type": "string", "format": "uri"}},
        "status": {"type": "string", "enum": ["ready", "claimed"]},
        "run_id": {"type": ["string", "null"]},
        "publish_date": {"type": ["string", "null"], "format": "date"},
    },
    "required": ["pack_id", "topic", "words", "image_urls", "status"],
    "additionalProperties": True,
}
