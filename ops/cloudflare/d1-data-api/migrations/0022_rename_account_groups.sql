-- 发布账号组名称与 MatrixMedia 登录分区统一为 finance、korean。
UPDATE publishing_account_groups
SET name = 'finance', updated_at = CURRENT_TIMESTAMP
WHERE code = 'finance-inspiration' OR name = '心灵鸡汤';

UPDATE publishing_account_group_members
SET account_ref = 'finance',
    display_name = 'finance',
    updated_at = CURRENT_TIMESTAMP
WHERE group_code = 'finance-inspiration' OR account_ref = '心灵鸡汤';

UPDATE publishing_account_groups
SET name = 'korean', updated_at = CURRENT_TIMESTAMP
WHERE code = 'language-korean' OR name = '韩语';

UPDATE publishing_account_group_members
SET account_ref = 'korean',
    display_name = 'korean',
    updated_at = CURRENT_TIMESTAMP
WHERE group_code = 'language-korean' OR account_ref IN ('韩语', '学韩语');
