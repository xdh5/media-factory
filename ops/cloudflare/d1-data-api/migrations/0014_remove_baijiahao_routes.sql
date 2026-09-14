-- 停止百家号后续发布：移除账号组中的百家号路由，保留历史发布记录。
DELETE FROM publishing_account_group_members
WHERE platform = 'baijiahao';
