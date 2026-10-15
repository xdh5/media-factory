-- 新增动漫 YouTube 账号组，扩展业务线约束并原样保留现有账号组和成员。
PRAGMA defer_foreign_keys = ON;

CREATE TABLE anime_group_members_preserved AS
SELECT * FROM publishing_account_group_members;

CREATE TABLE publishing_account_groups_anime (
    code TEXT PRIMARY KEY,
    name TEXT NOT NULL UNIQUE,
    business_line TEXT NOT NULL CHECK (business_line IN ('finance', 'language_learning', 'psychology_quiz', 'anime')),
    enabled INTEGER NOT NULL DEFAULT 1 CHECK (enabled IN (0, 1)),
    created_at TEXT NOT NULL DEFAULT CURRENT_TIMESTAMP,
    updated_at TEXT NOT NULL DEFAULT CURRENT_TIMESTAMP
);

INSERT INTO publishing_account_groups_anime
SELECT * FROM publishing_account_groups;

DROP TABLE publishing_account_groups;
ALTER TABLE publishing_account_groups_anime RENAME TO publishing_account_groups;

-- 删除父表可能触发成员级联删除，统一从本次事务内的临时副本恢复。
DELETE FROM publishing_account_group_members;
INSERT INTO publishing_account_group_members
SELECT * FROM anime_group_members_preserved;
DROP TABLE anime_group_members_preserved;

INSERT INTO publishing_account_groups(code, name, business_line)
VALUES ('anime', 'anime', 'anime');

-- 频道身份与凭据引用由部署者完成 OAuth 后配置，不在公共迁移中预置个人账号。

PRAGMA defer_foreign_keys = OFF;
