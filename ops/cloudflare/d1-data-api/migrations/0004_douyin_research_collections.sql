DROP INDEX IF EXISTS idx_douyin_research_created_at;
DROP INDEX IF EXISTS idx_douyin_research_keyword;

CREATE TABLE douyin_research_contents_new (
    aweme_id TEXT PRIMARY KEY,
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

INSERT INTO douyin_research_contents_new(
    aweme_id, author_name, published_at, caption, transcript_raw,
    transcript_corrected, aweme_url, cover_url, created_at, updated_at
)
SELECT
    aweme_id, author_name, published_at, caption, transcript_raw,
    transcript_corrected, aweme_url, cover_url, created_at, updated_at
FROM douyin_research_contents;

DROP TABLE douyin_research_contents;
ALTER TABLE douyin_research_contents_new RENAME TO douyin_research_contents;

CREATE INDEX idx_douyin_research_created_at
ON douyin_research_contents(created_at DESC);

CREATE TABLE douyin_research_collections (
    code TEXT PRIMARY KEY,
    name TEXT NOT NULL UNIQUE,
    created_at TEXT NOT NULL DEFAULT CURRENT_TIMESTAMP,
    updated_at TEXT NOT NULL DEFAULT CURRENT_TIMESTAMP
);

CREATE TABLE douyin_research_discoveries (
    id INTEGER PRIMARY KEY AUTOINCREMENT,
    aweme_id TEXT NOT NULL,
    collection_code TEXT NOT NULL,
    search_keyword TEXT NOT NULL,
    search_rank INTEGER NOT NULL,
    discovered_at TEXT NOT NULL DEFAULT CURRENT_TIMESTAMP,
    UNIQUE(aweme_id, collection_code, search_keyword),
    FOREIGN KEY(aweme_id) REFERENCES douyin_research_contents(aweme_id) ON DELETE CASCADE,
    FOREIGN KEY(collection_code) REFERENCES douyin_research_collections(code) ON DELETE RESTRICT
);

CREATE INDEX idx_douyin_research_discovery_collection
ON douyin_research_discoveries(collection_code, discovered_at DESC);

CREATE INDEX idx_douyin_research_discovery_keyword
ON douyin_research_discoveries(search_keyword, discovered_at DESC);

INSERT OR IGNORE INTO douyin_research_collections(code, name)
VALUES ('finance', '财经'), ('inspiration', '心灵鸡汤');
