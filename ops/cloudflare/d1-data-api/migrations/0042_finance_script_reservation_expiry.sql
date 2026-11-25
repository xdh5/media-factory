-- 每次领取保存实际到期时间；本次归还遗留的财经临时占用，保留已使用记录。
ALTER TABLE douyin_research_script_usage ADD COLUMN reservation_expires_at TEXT;
UPDATE douyin_research_script_usage
SET reservation_expires_at = datetime(reserved_at, '+120 minutes')
WHERE status = 'reserved';
DELETE FROM douyin_research_script_usage WHERE workflow = 'finance' AND status = 'reserved';
