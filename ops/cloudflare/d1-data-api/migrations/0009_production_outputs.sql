CREATE TABLE IF NOT EXISTS production_outputs (
    id INTEGER PRIMARY KEY AUTOINCREMENT,
    production_id TEXT NOT NULL UNIQUE,
    run_id TEXT NOT NULL,
    publish_date TEXT NOT NULL,
    business_line TEXT NOT NULL CHECK (business_line IN ('finance', 'language_learning')),
    content_kind TEXT NOT NULL,
    content_part INTEGER NOT NULL DEFAULT 1 CHECK (content_part >= 1),
    title TEXT NOT NULL,
    source TEXT NOT NULL CHECK (source IN ('local_mcp', 'github_workflow')),
    local_path TEXT,
    r2_url TEXT,
    created_at TEXT NOT NULL DEFAULT CURRENT_TIMESTAMP,
    updated_at TEXT NOT NULL DEFAULT CURRENT_TIMESTAMP,
    CHECK (local_path IS NOT NULL OR r2_url IS NOT NULL),
    CHECK (source != 'github_workflow' OR (local_path IS NULL AND r2_url IS NOT NULL)),
    UNIQUE (source, business_line, run_id, content_kind, content_part)
);

CREATE INDEX IF NOT EXISTS idx_production_outputs_date_line
ON production_outputs(publish_date DESC, business_line);

CREATE INDEX IF NOT EXISTS idx_production_outputs_run
ON production_outputs(run_id, business_line);

CREATE INDEX IF NOT EXISTS idx_production_outputs_source
ON production_outputs(source, publish_date DESC);
