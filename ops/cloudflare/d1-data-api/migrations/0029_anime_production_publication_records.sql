-- 扩展动漫产物与发布记录业务线，原样保留历史数据和索引。

CREATE TABLE publication_records_anime (
    id INTEGER PRIMARY KEY AUTOINCREMENT,
    publication_id TEXT NOT NULL,
    run_id TEXT NOT NULL,
    business_line TEXT NOT NULL CHECK (business_line IN ('finance', 'language_learning', 'psychology_quiz', 'anime')),
    platform TEXT NOT NULL CHECK (
        platform IN (
            'youtube', 'facebook', 'instagram', 'tiktok', 'kuaishou',
            'douyin', 'baijiahao', 'xiaohongshu', 'toutiao', 'wechat_channels'
        )
    ),
    connector TEXT NOT NULL,
    account_id TEXT NOT NULL DEFAULT '',
    content_part INTEGER NOT NULL DEFAULT 1 CHECK (content_part >= 1),
    title TEXT NOT NULL,
    publish_mode TEXT NOT NULL CHECK (publish_mode IN ('immediate', 'scheduled')),
    publish_at TEXT NOT NULL,
    status TEXT NOT NULL CHECK (status IN ('published', 'scheduled')),
    external_id TEXT,
    external_url TEXT,
    created_at TEXT NOT NULL DEFAULT CURRENT_TIMESTAMP,
    updated_at TEXT NOT NULL DEFAULT CURRENT_TIMESTAMP,
    UNIQUE (publication_id, platform, account_id, content_part)
);

INSERT INTO publication_records_anime SELECT * FROM publication_records;

DROP TABLE publication_records;

ALTER TABLE publication_records_anime RENAME TO publication_records;

CREATE INDEX idx_publication_records_business_time
ON publication_records(business_line, publish_at DESC);

CREATE INDEX idx_publication_records_platform_time
ON publication_records(platform, publish_at DESC);

CREATE UNIQUE INDEX uq_publication_records_content_platform_account
ON publication_records(business_line, run_id, title, platform, account_id, content_part);

CREATE TABLE production_outputs_anime (
    id INTEGER PRIMARY KEY AUTOINCREMENT,
    production_id TEXT NOT NULL UNIQUE,
    run_id TEXT NOT NULL,
    publish_date TEXT NOT NULL,
    business_line TEXT NOT NULL CHECK (business_line IN ('finance', 'language_learning', 'psychology_quiz', 'anime')),
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

INSERT INTO production_outputs_anime SELECT * FROM production_outputs;

DROP TABLE production_outputs;

ALTER TABLE production_outputs_anime RENAME TO production_outputs;

CREATE INDEX idx_production_outputs_date_line
ON production_outputs(publish_date DESC, business_line);

CREATE INDEX idx_production_outputs_run
ON production_outputs(run_id, business_line);

CREATE INDEX idx_production_outputs_source
ON production_outputs(source, publish_date DESC);
