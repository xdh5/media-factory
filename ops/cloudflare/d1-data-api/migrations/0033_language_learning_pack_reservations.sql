-- 制作中临时锁定；六条语言成片交付后才正式使用词包。
ALTER TABLE language_learning_packs ADD COLUMN reservation_expires_at TEXT;
ALTER TABLE language_learning_packs ADD COLUMN used_at TEXT;

UPDATE language_learning_packs
SET used_at = claimed_at
WHERE status = 'claimed' AND (
  SELECT COUNT(DISTINCT content_kind || ':' || content_part)
  FROM production_outputs
  WHERE business_line = 'language_learning' AND source = 'github_workflow'
    AND run_id = language_learning_packs.run_id AND r2_url IS NOT NULL
    AND ((content_kind IN ('en-zh', 'en-ko') AND content_part IN (1, 2))
      OR (content_kind IN ('en-zh-quiz', 'en-ko-quiz') AND content_part = 1))
) = 6;

UPDATE language_learning_packs
SET reservation_expires_at = strftime('%Y-%m-%dT%H:%M:%SZ', 'now', '+7 hours')
WHERE status = 'claimed' AND used_at IS NULL;
