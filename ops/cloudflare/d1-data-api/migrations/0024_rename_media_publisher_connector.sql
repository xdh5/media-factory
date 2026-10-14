-- 浏览器连接器名称从 matrixmedia 改为 media-publisher。
PRAGMA foreign_keys = OFF;

DROP TABLE IF EXISTS publishing_account_group_members_next;

CREATE TABLE publishing_account_group_members_next (
    id INTEGER PRIMARY KEY AUTOINCREMENT,
    group_code TEXT NOT NULL,
    platform TEXT NOT NULL CHECK (
        platform IN (
            'youtube', 'facebook', 'instagram', 'tiktok', 'kuaishou',
            'douyin', 'baijiahao', 'toutiao', 'wechat_channels'
        )
    ),
    connector TEXT NOT NULL CHECK (connector IN ('youtube', 'zernio', 'media-publisher')),
    account_ref TEXT NOT NULL,
    display_name TEXT NOT NULL DEFAULT '',
    position INTEGER NOT NULL DEFAULT 0,
    enabled INTEGER NOT NULL DEFAULT 1 CHECK (enabled IN (0, 1)),
    created_at TEXT NOT NULL DEFAULT CURRENT_TIMESTAMP,
    updated_at TEXT NOT NULL DEFAULT CURRENT_TIMESTAMP,
    platform_account_id TEXT NOT NULL DEFAULT '',
    UNIQUE(group_code, platform, connector, account_ref),
    FOREIGN KEY(group_code) REFERENCES publishing_account_groups(code) ON DELETE CASCADE
);

INSERT INTO publishing_account_group_members_next(
    id, group_code, platform, connector, account_ref, display_name, position,
    enabled, created_at, updated_at, platform_account_id
)
SELECT
    id, group_code, platform,
    CASE connector WHEN 'matrixmedia' THEN 'media-publisher' ELSE connector END,
    account_ref, display_name, position, enabled, created_at, updated_at, platform_account_id
FROM publishing_account_group_members;

DROP TABLE publishing_account_group_members;
ALTER TABLE publishing_account_group_members_next RENAME TO publishing_account_group_members;

CREATE INDEX idx_publishing_group_members_order
ON publishing_account_group_members(group_code, enabled, position, platform, id);

CREATE UNIQUE INDEX IF NOT EXISTS uq_publishing_group_platform_account
ON publishing_account_group_members(group_code, platform, platform_account_id)
WHERE platform_account_id <> '';

UPDATE publication_records
SET connector = 'media-publisher'
WHERE connector = 'matrixmedia';

PRAGMA foreign_keys = ON;
