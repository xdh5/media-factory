-- 账号组成员保存平台签发的真实账号 ID；连接器内部账号 ID 和 MatrixMedia 分区名不得写入此字段。
ALTER TABLE publishing_account_group_members
ADD COLUMN platform_account_id TEXT NOT NULL DEFAULT '';

UPDATE publishing_account_group_members
SET platform_account_id = CASE
    WHEN group_code = 'language-chinese' AND platform = 'youtube' THEN 'UC2WPS9jGyQF38pzj_j2EA5g'
    WHEN group_code = 'language-chinese' AND platform = 'tiktok' THEN '-000P4jzZ9hfCXPjUclo9KpODSnL3K5ye2sT'
    WHEN group_code = 'language-chinese' AND platform = 'instagram' THEN '27638488339166894'
    WHEN group_code = 'language-chinese' AND platform = 'facebook' THEN '1143305922209908'
    WHEN group_code = 'finance-inspiration' AND platform = 'douyin' THEN '5ebd27537c2d89f1a5a72c43e4a45647fa270e48ea2301c88b289707c079e4ae'
    WHEN group_code = 'finance-inspiration' AND platform = 'kuaishou' THEN '5669763434'
    WHEN group_code = 'finance-inspiration' AND platform = 'baijiahao' THEN 'a4b1cddf63dc85e60ec5e9fce5d05c'
    WHEN group_code = 'finance-inspiration' AND platform = 'toutiao' THEN '841084e7ef0558cdcd24170c00905387'
    WHEN group_code = 'finance-inspiration' AND platform = 'wechat_channels' THEN '1931719177'
    WHEN group_code = 'language-korean' AND platform = 'douyin' THEN '317184125206d66941f5754a4c62f981245f0b1d3384f513f776d54bca4de406'
    WHEN group_code = 'language-korean' AND platform = 'kuaishou' THEN '1462643737'
    ELSE platform_account_id
END;

CREATE UNIQUE INDEX IF NOT EXISTS uq_publishing_group_platform_account
ON publishing_account_group_members(group_code, platform, platform_account_id)
WHERE platform_account_id <> '';

-- 发布记录的 account_id 保存 platform_account_id，按内容、平台、真实账号和分段保持幂等。
CREATE UNIQUE INDEX IF NOT EXISTS uq_publication_records_content_platform_account
ON publication_records(business_line, title, platform, account_id, content_part);
