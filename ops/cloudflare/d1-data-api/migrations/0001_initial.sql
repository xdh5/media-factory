-- 仅存放可同步到云端的三张业务表，不包含矩阵媒体账号信息。
PRAGMA foreign_keys = ON;

CREATE TABLE IF NOT EXISTS topic_history (
    id INTEGER PRIMARY KEY AUTOINCREMENT,
    workflow TEXT NOT NULL,
    topic TEXT NOT NULL,
    fingerprint TEXT NOT NULL,
    status TEXT NOT NULL DEFAULT 'used',
    created_at TEXT NOT NULL,
    updated_at TEXT NOT NULL
);

CREATE INDEX IF NOT EXISTS idx_topic_history_lookup
ON topic_history(workflow, fingerprint, created_at, status);

CREATE TABLE IF NOT EXISTS language_learning_words (
    id INTEGER PRIMARY KEY AUTOINCREMENT,
    run_id TEXT NOT NULL,
    topic_record_id INTEGER NOT NULL,
    topic TEXT NOT NULL,
    english TEXT NOT NULL,
    normalized_english TEXT NOT NULL,
    word_json TEXT NOT NULL,
    created_at TEXT NOT NULL,
    UNIQUE(run_id, normalized_english),
    FOREIGN KEY(topic_record_id) REFERENCES topic_history(id)
);

CREATE INDEX IF NOT EXISTS idx_language_learning_words_recent
ON language_learning_words(normalized_english, created_at DESC);

CREATE TABLE IF NOT EXISTS image_library (
    line TEXT NOT NULL,
    id INTEGER NOT NULL,
    caption TEXT NOT NULL,
    image_path TEXT,
    created_at TEXT NOT NULL,
    updated_at TEXT NOT NULL,
    PRIMARY KEY (line, id)
);

