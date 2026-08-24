-- 发布记录按内容、平台、账号和分段保持幂等；同一内容不得因外部任务 ID 变化而重复入库。
CREATE UNIQUE INDEX IF NOT EXISTS uq_publication_records_content_platform_account
ON publication_records(business_line, title, platform, account_id, content_part);
