-- 账号组成员保存平台签发的真实账号 ID；连接器内部账号 ID 和 MatrixMedia 分区名不得写入此字段。
ALTER TABLE publishing_account_group_members
ADD COLUMN platform_account_id TEXT NOT NULL DEFAULT '';

CREATE UNIQUE INDEX IF NOT EXISTS uq_publishing_group_platform_account
ON publishing_account_group_members(group_code, platform, platform_account_id)
WHERE platform_account_id <> '';

-- 发布记录的 account_id 保存 platform_account_id，按内容、平台、真实账号和分段保持幂等。
CREATE UNIQUE INDEX IF NOT EXISTS uq_publication_records_content_platform_account
ON publication_records(business_line, title, platform, account_id, content_part);
