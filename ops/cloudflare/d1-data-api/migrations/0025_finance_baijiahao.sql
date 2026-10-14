-- 将现有财经百家号会话加入财经发布账号组。
INSERT INTO publishing_account_group_members (
    group_code, platform, connector, account_ref, display_name,
    position, enabled, platform_account_id
)
SELECT code, 'baijiahao', 'media-publisher', 'finance', 'finance',
       4, 1, 'finance'
FROM publishing_account_groups
WHERE name = 'finance' AND business_line = 'finance'
ON CONFLICT(group_code, platform, connector, account_ref) DO UPDATE SET
    enabled = 1,
    updated_at = CURRENT_TIMESTAMP;
