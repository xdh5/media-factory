-- 按作品记录首次采集审核结果，重试不会重复计入弃稿率。
CREATE TABLE finance_collection_reviews (
    aweme_id TEXT PRIMARY KEY,
    decision TEXT NOT NULL CHECK (decision IN ('normal', 'ad', 'off_topic', 'length')),
    reason TEXT NOT NULL,
    author_id TEXT NOT NULL,
    author_name TEXT NOT NULL,
    author_profile_url TEXT NOT NULL,
    source TEXT NOT NULL CHECK (source IN ('direct_link', 'author_homepage')),
    aweme_url TEXT NOT NULL,
    source_character_count INTEGER NOT NULL CHECK (source_character_count >= 0),
    created_at TEXT NOT NULL DEFAULT CURRENT_TIMESTAMP
);

CREATE INDEX idx_finance_collection_reviews_decision
ON finance_collection_reviews(decision, created_at DESC);
