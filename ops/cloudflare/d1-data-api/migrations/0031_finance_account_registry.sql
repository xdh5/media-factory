DELETE FROM publishing_accounts
WHERE account_key = 'finance_youtube'
  AND NOT EXISTS (
    SELECT 1 FROM publishing_account_group_members
    WHERE account_key = publishing_accounts.account_key
  );
