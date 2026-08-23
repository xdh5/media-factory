CREATE TABLE IF NOT EXISTS douyin_research_contents (
    aweme_id TEXT PRIMARY KEY,
    source_keyword TEXT NOT NULL,
    search_rank INTEGER NOT NULL,
    author_name TEXT NOT NULL,
    published_at TEXT,
    caption TEXT NOT NULL,
    transcript_raw TEXT NOT NULL,
    transcript_corrected TEXT NOT NULL,
    aweme_url TEXT NOT NULL,
    cover_url TEXT,
    created_at TEXT NOT NULL DEFAULT CURRENT_TIMESTAMP,
    updated_at TEXT NOT NULL DEFAULT CURRENT_TIMESTAMP
);

CREATE INDEX IF NOT EXISTS idx_douyin_research_created_at
ON douyin_research_contents(created_at DESC);

CREATE INDEX IF NOT EXISTS idx_douyin_research_keyword
ON douyin_research_contents(source_keyword, created_at DESC);
