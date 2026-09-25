INSERT OR IGNORE INTO douyin_research_collections(code, name)
VALUES ('finance', '财经');

INSERT OR IGNORE INTO douyin_research_discoveries(
    aweme_id,
    collection_code,
    search_keyword,
    search_rank,
    discovered_at
)
SELECT
    aweme_id,
    'finance',
    search_keyword,
    search_rank,
    discovered_at
FROM douyin_research_discoveries
WHERE collection_code = 'inspiration';

DELETE FROM douyin_research_discoveries
WHERE collection_code = 'inspiration';

DELETE FROM douyin_research_collections
WHERE code = 'inspiration' OR name = '心灵鸡汤';
