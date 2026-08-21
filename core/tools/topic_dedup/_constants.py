"""话题去重常量。"""

DEFAULT_DEDUPLICATION_DAYS = 30
TOPIC_DEDUP_SCHEMA_VERSION = 1
# 沿用旧表名，兼容已有 SQLite 数据
TOPIC_DEDUP_TABLE = "topic_history"
ACTIVE_TOPIC_STATUSES = ["reserved", "completed", "published", "used"]
SUPPORTED_TOPIC_STATUSES = [*ACTIVE_TOPIC_STATUSES, "failed"]
