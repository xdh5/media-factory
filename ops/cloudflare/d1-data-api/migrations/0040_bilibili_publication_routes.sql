-- B站发布路由和回执保留原有数据，扩展平台约束。
CREATE TABLE publishing_account_group_members_bilibili (
    id INTEGER PRIMARY KEY AUTOINCREMENT,
    group_code TEXT NOT NULL,
    platform TEXT NOT NULL CHECK (platform IN ('youtube','facebook','instagram','tiktok','kuaishou','douyin','baijiahao','toutiao','wechat_channels','bilibili')),
    connector TEXT NOT NULL CHECK (connector IN ('youtube','zernio','media-publisher')),
    account_ref TEXT NOT NULL,
    display_name TEXT NOT NULL DEFAULT '',
    position INTEGER NOT NULL DEFAULT 0,
    enabled INTEGER NOT NULL DEFAULT 1 CHECK (enabled IN (0,1)),
    created_at TEXT NOT NULL DEFAULT CURRENT_TIMESTAMP,
    updated_at TEXT NOT NULL DEFAULT CURRENT_TIMESTAMP,
    platform_account_id TEXT NOT NULL DEFAULT '',
    account_key TEXT REFERENCES publishing_accounts(account_key),
    UNIQUE(group_code,platform,connector,account_ref),
    FOREIGN KEY(group_code) REFERENCES publishing_account_groups(code) ON DELETE CASCADE
);
INSERT INTO publishing_account_group_members_bilibili SELECT * FROM publishing_account_group_members;
DROP TABLE publishing_account_group_members;
ALTER TABLE publishing_account_group_members_bilibili RENAME TO publishing_account_group_members;
CREATE INDEX idx_publishing_group_members_order ON publishing_account_group_members(group_code,enabled,position,platform,id);
CREATE UNIQUE INDEX uq_publishing_group_platform_account ON publishing_account_group_members(group_code,platform,platform_account_id) WHERE platform_account_id <> '';
CREATE UNIQUE INDEX uq_publishing_group_account ON publishing_account_group_members(group_code,account_key) WHERE account_key IS NOT NULL;

CREATE TABLE publication_records_bilibili (
    id INTEGER PRIMARY KEY AUTOINCREMENT,
    publication_id TEXT NOT NULL,
    run_id TEXT NOT NULL,
    business_line TEXT NOT NULL CHECK (business_line IN ('finance','language_learning','psychology_quiz','anime')),
    platform TEXT NOT NULL CHECK (platform IN ('youtube','facebook','instagram','tiktok','kuaishou','douyin','baijiahao','xiaohongshu','toutiao','wechat_channels','bilibili')),
    connector TEXT NOT NULL,
    account_id TEXT NOT NULL DEFAULT '',
    content_part INTEGER NOT NULL DEFAULT 1 CHECK (content_part >= 1),
    title TEXT NOT NULL,
    publish_mode TEXT NOT NULL CHECK (publish_mode IN ('immediate','scheduled')),
    publish_at TEXT NOT NULL,
    status TEXT NOT NULL CHECK (status IN ('published','scheduled')),
    external_id TEXT,
    external_url TEXT,
    created_at TEXT NOT NULL DEFAULT CURRENT_TIMESTAMP,
    updated_at TEXT NOT NULL DEFAULT CURRENT_TIMESTAMP,
    UNIQUE(publication_id,platform,account_id,content_part)
);
INSERT INTO publication_records_bilibili SELECT * FROM publication_records;
DROP TABLE publication_records;
ALTER TABLE publication_records_bilibili RENAME TO publication_records;
CREATE INDEX idx_publication_records_business_time ON publication_records(business_line,publish_at DESC);
CREATE INDEX idx_publication_records_platform_time ON publication_records(platform,publish_at DESC);
CREATE UNIQUE INDEX uq_publication_records_content_platform_account ON publication_records(business_line,run_id,title,platform,account_id,content_part) WHERE business_line NOT IN ('language_learning','finance');
