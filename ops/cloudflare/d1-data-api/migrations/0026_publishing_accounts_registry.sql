-- 账号身份与账号组成员分离，凭据仅保存引用。
CREATE TABLE publishing_accounts (
    account_key TEXT PRIMARY KEY,
    platform TEXT NOT NULL CHECK (platform IN ('youtube', 'tiktok', 'instagram', 'facebook')),
    connector TEXT NOT NULL CHECK (connector IN ('youtube', 'zernio')),
    connector_account_id TEXT NOT NULL,
    platform_account_id TEXT NOT NULL,
    display_name TEXT NOT NULL DEFAULT '',
    credential_ref TEXT NOT NULL,
    enabled INTEGER NOT NULL DEFAULT 1 CHECK (enabled IN (0, 1)),
    created_at TEXT NOT NULL DEFAULT CURRENT_TIMESTAMP,
    updated_at TEXT NOT NULL DEFAULT CURRENT_TIMESTAMP,
    UNIQUE(platform, platform_account_id)
);

ALTER TABLE publishing_account_group_members
ADD COLUMN account_key TEXT REFERENCES publishing_accounts(account_key);

INSERT INTO publishing_accounts (
    account_key, platform, connector, connector_account_id, platform_account_id, display_name, credential_ref
) VALUES
    ('chinese_youtube', 'youtube', 'youtube', 'UC2WPS9jGyQF38pzj_j2EA5g', 'UC2WPS9jGyQF38pzj_j2EA5g', 'Daily Chinese Learning', 'youtube_chinese'),
    ('chinese_tiktok', 'tiktok', 'zernio', '6a89bfe377555aae01616178', '-000P4jzZ9hfCXPjUclo9KpODSnL3K5ye2sT', 'Daily Chinese', 'zernio_tiktok'),
    ('chinese_instagram', 'instagram', 'zernio', '6a8b4ef377555aae01b3fdd6', '27638488339166894', 'Daily Chinese Learning', 'zernio_meta'),
    ('chinese_facebook', 'facebook', 'zernio', '6a8b4f7d77555aae01b41f25', '1143305922209908', 'Daily Chinese Learning', 'zernio_meta');

UPDATE publishing_account_group_members
SET account_key = 'chinese_' || platform,
    account_ref = 'chinese_' || platform,
    updated_at = CURRENT_TIMESTAMP
WHERE group_code = 'language-chinese'
  AND platform IN ('youtube', 'tiktok', 'instagram', 'facebook');

CREATE UNIQUE INDEX uq_publishing_group_account
ON publishing_account_group_members(group_code, account_key)
WHERE account_key IS NOT NULL;
