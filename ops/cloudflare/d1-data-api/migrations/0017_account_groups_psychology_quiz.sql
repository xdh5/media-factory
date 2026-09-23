-- 0017: publishing_account_groups 的 business_line CHECK 约束缺少 psychology_quiz，
-- 心灵鸡汤账号组只能挂在 finance 名下，导致 psychology_quiz 成片发布时
-- resolve_account_group 报“账号组属于 finance，不能用于 psychology_quiz”。
-- 心灵鸡汤组（douyin/kuaishou/toutiao/wechat_channels，MatrixMedia）专属该内容线，改挂 psychology_quiz。
DROP TABLE IF EXISTS publishing_account_groups_new;

CREATE TABLE publishing_account_groups_new (
    code TEXT PRIMARY KEY,
    name TEXT NOT NULL UNIQUE,
    business_line TEXT NOT NULL CHECK (business_line IN ('finance', 'language_learning', 'psychology_quiz')),
    enabled INTEGER NOT NULL DEFAULT 1 CHECK (enabled IN (0, 1)),
    created_at TEXT NOT NULL DEFAULT CURRENT_TIMESTAMP,
    updated_at TEXT NOT NULL DEFAULT CURRENT_TIMESTAMP
);

INSERT INTO publishing_account_groups_new (code, name, business_line, enabled, created_at, updated_at)
SELECT code, name, business_line, enabled, created_at, updated_at
FROM publishing_account_groups;

DROP TABLE publishing_account_groups;
ALTER TABLE publishing_account_groups_new RENAME TO publishing_account_groups;

UPDATE publishing_account_groups
SET business_line = 'psychology_quiz', updated_at = CURRENT_TIMESTAMP
WHERE name = '心灵鸡汤';
