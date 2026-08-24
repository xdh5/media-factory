-- 财经千问生图独立图库；编号与 data/image_library_finance/<id>.png 保持一致。
CREATE TABLE IF NOT EXISTS finance_generated_images (
    line TEXT NOT NULL DEFAULT 'finance_generated',
    id INTEGER PRIMARY KEY AUTOINCREMENT,
    caption TEXT NOT NULL,
    image_path TEXT NOT NULL UNIQUE,
    created_at TEXT NOT NULL,
    updated_at TEXT NOT NULL
);

CREATE INDEX IF NOT EXISTS idx_finance_generated_images_line_id
ON finance_generated_images(line, id);
