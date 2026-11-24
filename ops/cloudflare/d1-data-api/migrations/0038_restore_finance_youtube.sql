-- 恢复原财经 YouTube 频道，凭据继续使用原有引用。
INSERT INTO publishing_accounts(account_key, platform, connector, connector_account_id, platform_account_id, display_name, credential_ref)
VALUES ('finance_youtube', 'youtube', 'youtube', 'UCtQyAESKMKLBpH8-mY-XMpw', 'UCtQyAESKMKLBpH8-mY-XMpw', '大鹅说', 'youtube_finance')
ON CONFLICT(account_key) DO UPDATE SET enabled=1, updated_at=CURRENT_TIMESTAMP;

INSERT INTO publishing_account_group_members(group_code, platform, connector, account_ref, display_name, position, enabled, account_key, platform_account_id)
VALUES ('finance-inspiration', 'youtube', 'youtube', 'finance_youtube', '大鹅说', 10, 1, 'finance_youtube', 'UCtQyAESKMKLBpH8-mY-XMpw')
ON CONFLICT(group_code, platform, connector, account_ref) DO UPDATE SET enabled=1, account_key=excluded.account_key, updated_at=CURRENT_TIMESTAMP;
