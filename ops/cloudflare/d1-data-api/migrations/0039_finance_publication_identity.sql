-- 财经长短视频及图文按产物标识分别保存，允许同一期同标题。
DROP INDEX uq_publication_records_content_platform_account;
CREATE UNIQUE INDEX uq_publication_records_content_platform_account
ON publication_records(business_line, run_id, title, platform, account_id, content_part)
WHERE business_line NOT IN ('language_learning', 'finance');
