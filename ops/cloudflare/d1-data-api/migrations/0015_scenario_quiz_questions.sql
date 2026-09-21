CREATE TABLE IF NOT EXISTS scenario_quiz_questions (
    id INTEGER PRIMARY KEY AUTOINCREMENT,
    run_id TEXT NOT NULL UNIQUE,
    topic_record_id INTEGER NOT NULL,
    topic TEXT NOT NULL,
    category TEXT NOT NULL CHECK (category IN ('finance', 'success', 'human_nature')),
    scene_title TEXT NOT NULL,
    scenario TEXT NOT NULL,
    option_a TEXT NOT NULL,
    option_b TEXT NOT NULL,
    option_c TEXT NOT NULL,
    option_d TEXT NOT NULL,
    result_a TEXT NOT NULL,
    result_b TEXT NOT NULL,
    result_c TEXT NOT NULL,
    result_d TEXT NOT NULL,
    image_keywords_json TEXT NOT NULL DEFAULT '[]',
    status TEXT NOT NULL DEFAULT 'reserved' CHECK (status IN ('reserved', 'used', 'rejected')),
    publish_date TEXT NOT NULL,
    created_at TEXT NOT NULL DEFAULT CURRENT_TIMESTAMP,
    updated_at TEXT NOT NULL DEFAULT CURRENT_TIMESTAMP
);

CREATE INDEX IF NOT EXISTS idx_scenario_quiz_questions_topic
ON scenario_quiz_questions(topic, created_at DESC);

CREATE INDEX IF NOT EXISTS idx_scenario_quiz_questions_publish_date
ON scenario_quiz_questions(publish_date DESC);
