-- 保留有效的 1～19；废弃的 20～38 已删除，把新批次 39～57 重排为 20～38。
CREATE TABLE finance_generated_images_next (
    line TEXT NOT NULL DEFAULT 'finance_generated',
    id INTEGER PRIMARY KEY AUTOINCREMENT,
    caption TEXT NOT NULL,
    image_path TEXT NOT NULL UNIQUE,
    created_at TEXT NOT NULL,
    updated_at TEXT NOT NULL
);

INSERT INTO finance_generated_images_next(
    id, line, caption, image_path, created_at, updated_at
)
SELECT
    CASE WHEN id >= 39 THEN id - 19 ELSE id END,
    'finance_generated',
    caption,
    'data/image_library_finance/' || CAST(
        CASE WHEN id >= 39 THEN id - 19 ELSE id END AS TEXT
    ) || '.png',
    created_at,
    updated_at
FROM finance_generated_images
WHERE id BETWEEN 1 AND 19
   OR id BETWEEN 39 AND 57
   OR (
       id BETWEEN 20 AND 38
       AND NOT EXISTS (
           SELECT 1 FROM finance_generated_images AS newer
           WHERE newer.id BETWEEN 39 AND 57
       )
   )
ORDER BY id;

DROP TABLE finance_generated_images;
ALTER TABLE finance_generated_images_next RENAME TO finance_generated_images;

CREATE INDEX idx_finance_generated_images_line_id
ON finance_generated_images(line, id);
