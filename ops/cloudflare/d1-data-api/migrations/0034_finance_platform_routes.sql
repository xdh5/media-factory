DELETE FROM publishing_account_group_members
WHERE platform = 'baijiahao'
  AND group_code IN (
    SELECT code FROM publishing_account_groups WHERE business_line = 'finance'
  );
