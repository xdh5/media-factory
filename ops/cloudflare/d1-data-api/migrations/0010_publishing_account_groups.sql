-- 统一发布账号组只保存路由标识，不保存密码、Cookie、Token 或手机号凭据。
PRAGMA foreign_keys = ON;

CREATE TABLE publishing_account_groups (
    code TEXT PRIMARY KEY,
    name TEXT NOT NULL UNIQUE,
    business_line TEXT NOT NULL CHECK (business_line IN ('finance', 'language_learning')),
    enabled INTEGER NOT NULL DEFAULT 1 CHECK (enabled IN (0, 1)),
    created_at TEXT NOT NULL DEFAULT CURRENT_TIMESTAMP,
    updated_at TEXT NOT NULL DEFAULT CURRENT_TIMESTAMP
);

CREATE TABLE publishing_account_group_members (
    id INTEGER PRIMARY KEY AUTOINCREMENT,
    group_code TEXT NOT NULL,
    platform TEXT NOT NULL CHECK (
        platform IN (
            'youtube', 'facebook', 'instagram', 'tiktok', 'kuaishou',
            'douyin', 'baijiahao', 'toutiao', 'wechat_channels'
        )
    ),
    connector TEXT NOT NULL CHECK (connector IN ('youtube', 'zernio', 'matrixmedia')),
    account_ref TEXT NOT NULL,
    display_name TEXT NOT NULL DEFAULT '',
    position INTEGER NOT NULL DEFAULT 0,
    enabled INTEGER NOT NULL DEFAULT 1 CHECK (enabled IN (0, 1)),
    created_at TEXT NOT NULL DEFAULT CURRENT_TIMESTAMP,
    updated_at TEXT NOT NULL DEFAULT CURRENT_TIMESTAMP,
    UNIQUE(group_code, platform, connector, account_ref),
    FOREIGN KEY(group_code) REFERENCES publishing_account_groups(code) ON DELETE CASCADE
);

CREATE INDEX idx_publishing_group_members_order
ON publishing_account_group_members(group_code, enabled, position, platform, id);

INSERT INTO publishing_account_groups(code, name, business_line)
VALUES
    ('finance-inspiration', '心灵鸡汤', 'finance'),
    ('language-korean', '韩语', 'language_learning'),
    ('language-chinese', '中文', 'language_learning');

INSERT INTO publishing_account_group_members(
    group_code, platform, connector, account_ref, display_name, position
)
VALUES
    ('language-chinese', 'youtube', 'youtube', 'language_learning', '中文 YouTube', 10),
    ('language-chinese', 'tiktok', 'zernio', 'language_learning', '中文 TikTok', 20),
    ('language-chinese', 'instagram', 'zernio', 'configured', '中文 Instagram', 30),
    ('language-chinese', 'facebook', 'zernio', 'configured', '中文 Facebook', 40),
    ('finance-inspiration', 'douyin', 'matrixmedia', '心灵鸡汤', '心灵鸡汤抖音', 10),
    ('finance-inspiration', 'kuaishou', 'matrixmedia', '心灵鸡汤', '心灵鸡汤快手', 20),
    ('finance-inspiration', 'baijiahao', 'matrixmedia', '心灵鸡汤', '心灵鸡汤百家号', 30),
    ('finance-inspiration', 'toutiao', 'matrixmedia', '心灵鸡汤', '心灵鸡汤头条号', 40),
    ('finance-inspiration', 'wechat_channels', 'matrixmedia', '心灵鸡汤', '心灵鸡汤视频号', 50),
    ('language-korean', 'douyin', 'matrixmedia', '韩语', '韩语抖音', 10),
    ('language-korean', 'kuaishou', 'matrixmedia', '韩语', '韩语快手', 20),
    ('language-korean', 'baijiahao', 'matrixmedia', '韩语', '韩语百家号', 30),
    ('language-korean', 'toutiao', 'matrixmedia', '韩语', '韩语头条号', 40),
    ('language-korean', 'wechat_channels', 'matrixmedia', '韩语', '韩语视频号', 50);
