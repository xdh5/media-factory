-- 远程图库已经采用统一路径和连续编号，保留全部现有记录，仅确保索引存在。
CREATE INDEX IF NOT EXISTS idx_finance_generated_images_line_id
ON finance_generated_images(line, id);
