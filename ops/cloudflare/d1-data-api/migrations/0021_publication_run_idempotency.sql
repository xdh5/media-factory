-- 同名标题可以在不同生产日期再次发布，不能覆盖其他日期的历史记录。
DROP INDEX IF EXISTS uq_publication_records_content_platform_account;
CREATE UNIQUE INDEX uq_publication_records_content_platform_account
ON publication_records(business_line, run_id, title, platform, account_id, content_part);
