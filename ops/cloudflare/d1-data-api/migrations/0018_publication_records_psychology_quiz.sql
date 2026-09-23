-- 0018: publication_records 的 business_line CHECK 约束缺少 psychology_quiz，
-- 心灵鸡汤（文章模式）成片发布成功后写发布记录报 D1_ERROR，
-- 导致预约成功的平台无去重记录、其余平台中断。按标准流程重建表。
DROP TABLE IF EXISTS publication_records_new;

CREATE TABLE publication_records_new (
    id INTEGER PRIMARY KEY AUTOINCREMENT,
    publication_id TEXT NOT NULL,
    run_id TEXT NOT NULL,
    business_line TEXT NOT NULL CHECK (business_line IN ('finance', 'language_learning', 'psychology_quiz')),
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

INSERT INTO publication_records_new (
    id, publication_id, run_id, business_line, platform, connector, account_id,
    content_part, title, publish_mode, publish_at, status, external_id, external_url,
    created_at, updated_at
)
SELECT
    id, publication_id, run_id, business_line, platform, connector, account_id,
    content_part, title, publish_mode, publish_at, status, external_id, external_url,
    created_at, updated_at
FROM publication_records;

DROP TABLE publication_records;
ALTER TABLE publication_records_new RENAME TO publication_records;

CREATE INDEX idx_publication_records_business_time
ON publication_records(business_line, publish_at DESC);

CREATE INDEX idx_publication_records_platform_time
ON publication_records(platform, publish_at DESC);

CREATE UNIQUE INDEX uq_publication_records_content_platform_account
ON publication_records(business_line, title, platform, account_id, content_part);
