-- 看板展示长标题与发布标签，并显式记录 R2 下载地址的过期时间。
ALTER TABLE production_outputs
ADD COLUMN hashtags TEXT NOT NULL DEFAULT '';

ALTER TABLE production_outputs
ADD COLUMN r2_expires_at TEXT;

-- 回填当前已存在的财经本地产物。
UPDATE production_outputs
SET hashtags = '#被动收入 #财富思维 #普通人理财 #个人成长'
WHERE business_line = 'finance'
  AND title = '普通人真正的被动收入都藏在这四种资产里'
  AND hashtags = '';
