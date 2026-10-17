CREATE TABLE finance_editorial_drafts (
    aweme_id TEXT PRIMARY KEY REFERENCES douyin_research_contents(aweme_id) ON DELETE CASCADE,
    source_transcript TEXT NOT NULL,
    content_json TEXT NOT NULL CHECK(json_valid(content_json)),
    created_at TEXT NOT NULL DEFAULT CURRENT_TIMESTAMP,
    updated_at TEXT NOT NULL DEFAULT CURRENT_TIMESTAMP
);
