-- 删除已废弃的通用图库与发布账号路由配置，新增统一发布记录。
PRAGMA foreign_keys = ON;

DROP TABLE IF EXISTS publish_account_group_members;
DROP TABLE IF EXISTS publish_accounts;
DROP TABLE IF EXISTS publish_account_groups;
DROP TABLE IF EXISTS image_library;

CREATE TABLE publication_records (
    id INTEGER PRIMARY KEY AUTOINCREMENT,
    publication_id TEXT NOT NULL,
    run_id TEXT NOT NULL,
    business_line TEXT NOT NULL CHECK (business_line IN ('finance', 'language_learning')),
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
    UNIQUE(publication_id, platform, account_id, content_part)
);

CREATE INDEX idx_publication_records_business_time
ON publication_records(business_line, publish_at DESC);

CREATE INDEX idx_publication_records_platform_time
ON publication_records(platform, publish_at DESC);
