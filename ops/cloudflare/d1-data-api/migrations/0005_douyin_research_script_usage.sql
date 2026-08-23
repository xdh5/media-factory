CREATE TABLE IF NOT EXISTS douyin_research_script_usage (
    aweme_id TEXT NOT NULL,
    workflow TEXT NOT NULL,
    status TEXT NOT NULL CHECK(status IN ('reserved', 'used')),
    reservation_token TEXT NOT NULL,
    reserved_at TEXT NOT NULL,
    used_at TEXT,
    run_id TEXT,
    PRIMARY KEY(aweme_id, workflow),
    UNIQUE(reservation_token),
    FOREIGN KEY(aweme_id) REFERENCES douyin_research_contents(aweme_id) ON DELETE CASCADE
);

CREATE INDEX IF NOT EXISTS idx_douyin_research_script_usage_status
ON douyin_research_script_usage(workflow, status, reserved_at);
