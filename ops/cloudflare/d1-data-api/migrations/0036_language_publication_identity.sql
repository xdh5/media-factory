-- 同日语言原版与问答版可以使用相同标题，按产物标识区分。
DROP INDEX uq_publication_records_content_platform_account;
CREATE UNIQUE INDEX uq_publication_records_content_platform_account
ON publication_records(business_line, run_id, title, platform, account_id, content_part)
WHERE business_line != 'language_learning';
