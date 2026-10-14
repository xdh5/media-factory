-- 中文学习账号组名称与四个海外平台的登录前缀统一为 chinese。
UPDATE publishing_account_groups
SET name = 'chinese', updated_at = CURRENT_TIMESTAMP
WHERE code = 'language-chinese' OR name = '中文';

UPDATE publishing_account_group_members
SET account_ref = 'chinese',
    updated_at = CURRENT_TIMESTAMP
WHERE group_code = 'language-chinese';
