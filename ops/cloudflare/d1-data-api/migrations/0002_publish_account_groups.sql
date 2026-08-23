-- 发布账号组只保存路由别名，不保存密码、Cookie、Token 或手机号。
PRAGMA foreign_keys = ON;

CREATE TABLE IF NOT EXISTS publish_account_groups (
    code TEXT PRIMARY KEY,
    name TEXT NOT NULL UNIQUE,
    workflow TEXT NOT NULL,
    enabled INTEGER NOT NULL DEFAULT 1 CHECK (enabled IN (0, 1)),
    created_at TEXT NOT NULL,
    updated_at TEXT NOT NULL
);

CREATE TABLE IF NOT EXISTS publish_accounts (
    code TEXT PRIMARY KEY,
    platform TEXT NOT NULL,
    display_name TEXT NOT NULL,
    connector TEXT NOT NULL,
    config_key TEXT NOT NULL,
    config_json TEXT NOT NULL DEFAULT '{}',
    enabled INTEGER NOT NULL DEFAULT 1 CHECK (enabled IN (0, 1)),
    created_at TEXT NOT NULL,
    updated_at TEXT NOT NULL,
    UNIQUE(platform, config_key)
);

CREATE TABLE IF NOT EXISTS publish_account_group_members (
    group_code TEXT NOT NULL,
    account_code TEXT NOT NULL,
    position INTEGER NOT NULL DEFAULT 0,
    enabled INTEGER NOT NULL DEFAULT 1 CHECK (enabled IN (0, 1)),
    created_at TEXT NOT NULL,
    updated_at TEXT NOT NULL,
    PRIMARY KEY (group_code, account_code),
    FOREIGN KEY(group_code) REFERENCES publish_account_groups(code) ON DELETE CASCADE,
    FOREIGN KEY(account_code) REFERENCES publish_accounts(code) ON DELETE CASCADE
);

CREATE INDEX IF NOT EXISTS idx_publish_group_members_order
ON publish_account_group_members(group_code, enabled, position, account_code);

INSERT INTO publish_account_groups(code, name, workflow, enabled, created_at, updated_at)
VALUES
    ('learn-korean', '韩语', 'language_learning', 1, CURRENT_TIMESTAMP, CURRENT_TIMESTAMP),
    ('inspiration', '心灵鸡汤', 'finance', 1, CURRENT_TIMESTAMP, CURRENT_TIMESTAMP),
    ('learn-chinese', '中文', 'language_learning', 1, CURRENT_TIMESTAMP, CURRENT_TIMESTAMP)
ON CONFLICT(code) DO UPDATE SET
    name = excluded.name,
    workflow = excluded.workflow,
    enabled = excluded.enabled,
    updated_at = CURRENT_TIMESTAMP;

INSERT INTO publish_accounts(
    code, platform, display_name, connector, config_key, config_json, enabled, created_at, updated_at
)
VALUES
    (
        'matrixmedia-korean', 'matrixmedia', 'MatrixMedia 韩语', 'matrixmedia', '韩语',
        '{"account_group":"韩语"}', 1, CURRENT_TIMESTAMP, CURRENT_TIMESTAMP
    ),
    (
        'matrixmedia-inspiration', 'matrixmedia', 'MatrixMedia 心灵鸡汤', 'matrixmedia', '心灵鸡汤',
        '{"account_group":"心灵鸡汤"}', 1, CURRENT_TIMESTAMP, CURRENT_TIMESTAMP
    ),
    (
        'youtube-daily-chinese', 'youtube', 'YouTube Daily Chinese Learning', 'youtube', 'language_learning',
        '{"account":"language_learning","channel_title":"Daily Chinese Learning"}', 1, CURRENT_TIMESTAMP, CURRENT_TIMESTAMP
    ),
    (
        'meta-daily-chinese', 'meta', 'Meta Daily Chinese Learning', 'meta_scheduler', 'daily-chinese-learning',
        '{"account":"daily-chinese-learning","facebook_page":"Daily Chinese Learning","instagram":"chineseisland","crosspost":true}',
        1, CURRENT_TIMESTAMP, CURRENT_TIMESTAMP
    )
ON CONFLICT(code) DO UPDATE SET
    platform = excluded.platform,
    display_name = excluded.display_name,
    connector = excluded.connector,
    config_key = excluded.config_key,
    config_json = excluded.config_json,
    enabled = excluded.enabled,
    updated_at = CURRENT_TIMESTAMP;

INSERT INTO publish_account_group_members(
    group_code, account_code, position, enabled, created_at, updated_at
)
VALUES
    ('learn-korean', 'matrixmedia-korean', 10, 1, CURRENT_TIMESTAMP, CURRENT_TIMESTAMP),
    ('inspiration', 'matrixmedia-inspiration', 10, 1, CURRENT_TIMESTAMP, CURRENT_TIMESTAMP),
    ('learn-chinese', 'youtube-daily-chinese', 10, 1, CURRENT_TIMESTAMP, CURRENT_TIMESTAMP),
    ('learn-chinese', 'meta-daily-chinese', 20, 1, CURRENT_TIMESTAMP, CURRENT_TIMESTAMP)
ON CONFLICT(group_code, account_code) DO UPDATE SET
    position = excluded.position,
    enabled = excluded.enabled,
    updated_at = CURRENT_TIMESTAMP;
