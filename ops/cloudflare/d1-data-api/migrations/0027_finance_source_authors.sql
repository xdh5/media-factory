-- 财经采集使用的固定作者名单，可随时增减。
CREATE TABLE finance_source_authors (
    sec_user_id TEXT PRIMARY KEY,
    profile_url TEXT NOT NULL UNIQUE,
    display_name TEXT NOT NULL DEFAULT '',
    created_at TEXT NOT NULL DEFAULT CURRENT_TIMESTAMP,
    updated_at TEXT NOT NULL DEFAULT CURRENT_TIMESTAMP
);

CREATE INDEX idx_finance_source_authors_created_at
ON finance_source_authors(created_at ASC);

-- 整篇广告不再重复下载。正文里删掉的插入广告仍会入库。
CREATE TABLE finance_rejected_awemes (
    aweme_id TEXT PRIMARY KEY,
    reason TEXT NOT NULL CHECK (reason IN ('ad')),
    created_at TEXT NOT NULL DEFAULT CURRENT_TIMESTAMP
);
