ALTER TABLE topic_history ADD COLUMN publication_id TEXT;

CREATE UNIQUE INDEX IF NOT EXISTS idx_topic_history_publication
ON topic_history(publication_id)
WHERE publication_id IS NOT NULL;
