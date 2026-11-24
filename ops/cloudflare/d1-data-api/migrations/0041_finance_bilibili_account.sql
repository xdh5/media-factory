-- 将扫码验证过的财经B站账号加入原账号组。
INSERT INTO publishing_account_group_members(group_code,platform,connector,account_ref,display_name,position,enabled,platform_account_id)
VALUES ('finance-inspiration','bilibili','media-publisher','finance','大鹅说goose',5,1,'3747587582594827')
ON CONFLICT(group_code,platform,connector,account_ref) DO UPDATE SET platform_account_id=excluded.platform_account_id,display_name=excluded.display_name,enabled=1,updated_at=CURRENT_TIMESTAMP;
