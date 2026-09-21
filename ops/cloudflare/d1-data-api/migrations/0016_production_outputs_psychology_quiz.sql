-- 0016: production_outputs 的 business_line CHECK 约束缺少 psychology_quiz，
-- 导致心灵鸡汤（文章模式）成片记录无法写入 D1（D1_ERROR）。
-- SQLite 无法修改 CHECK 约束，按标准流程重建表。
DROP TABLE IF EXISTS production_outputs_new;

CREATE TABLE IF NOT EXISTS production_outputs_new (
    id INTEGER PRIMARY KEY AUTOINCREMENT,
    production_id TEXT NOT NULL UNIQUE,
    run_id TEXT NOT NULL,
    publish_date TEXT NOT NULL,
    business_line TEXT NOT NULL CHECK (business_line IN ('finance', 'language_learning', 'psychology_quiz')),
    content_kind TEXT NOT NULL,
    content_part INTEGER NOT NULL DEFAULT 1 CHECK (content_part >= 1),
    title TEXT NOT NULL,
    source TEXT NOT NULL CHECK (source IN ('local_mcp', 'github_workflow')),
    local_path TEXT,
    r2_url TEXT,
    r2_expires_at TEXT,
    hashtags TEXT NOT NULL DEFAULT '',
    created_at TEXT NOT NULL DEFAULT CURRENT_TIMESTAMP,
    updated_at TEXT NOT NULL DEFAULT CURRENT_TIMESTAMP,
    CHECK (local_path IS NOT NULL OR r2_url IS NOT NULL),
    CHECK (source != 'github_workflow' OR (local_path IS NULL AND r2_url IS NOT NULL)),
    UNIQUE (source, business_line, run_id, content_kind, content_part)
);

INSERT INTO production_outputs_new (
    id, production_id, run_id, publish_date, business_line, content_kind,
    content_part, title, hashtags, source, local_path, r2_url, r2_expires_at,
    created_at, updated_at
)
SELECT
    id, production_id, run_id, publish_date, business_line, content_kind,
    content_part, title, hashtags, source, local_path, r2_url, r2_expires_at,
    created_at, updated_at
FROM production_outputs;

DROP TABLE production_outputs;
ALTER TABLE production_outputs_new RENAME TO production_outputs;

CREATE INDEX IF NOT EXISTS idx_production_outputs_date_line
ON production_outputs(publish_date DESC, business_line);

CREATE INDEX IF NOT EXISTS idx_production_outputs_run
ON production_outputs(run_id, business_line);

CREATE INDEX IF NOT EXISTS idx_production_outputs_source
ON production_outputs(source, publish_date DESC);
