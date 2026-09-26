CREATE TABLE IF NOT EXISTS language_learning_packs (
    pack_id TEXT PRIMARY KEY,
    topic TEXT NOT NULL COLLATE NOCASE,
    words_json TEXT NOT NULL,
    image_urls_json TEXT NOT NULL,
    status TEXT NOT NULL CHECK (status IN ('ready', 'claimed')),
    run_id TEXT,
    publish_date TEXT,
    claimed_at TEXT,
    created_at TEXT NOT NULL DEFAULT CURRENT_TIMESTAMP,
    updated_at TEXT NOT NULL DEFAULT CURRENT_TIMESTAMP,
    CHECK ((status = 'ready' AND run_id IS NULL AND publish_date IS NULL) OR
           (status = 'claimed' AND run_id IS NOT NULL AND publish_date IS NOT NULL))
);

CREATE INDEX IF NOT EXISTS idx_language_learning_packs_ready
ON language_learning_packs(status, created_at);
