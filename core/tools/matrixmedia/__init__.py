"""MatrixMedia CLI 工具公开入口。"""

from .matrixmedia_cli import list_accounts, list_history, login_account, publish_video
from .account_groups import (
    add_accounts_to_group,
    create_account_group,
    delete_account_group,
    list_account_groups,
    list_registered_accounts,
    migrate_windows_profile,
    publish_to_group,
    register_account,
    remove_accounts_from_group,
)

__all__ = [
    "publish_video", "list_accounts", "list_history", "login_account",
    "register_account", "list_registered_accounts", "create_account_group",
    "add_accounts_to_group", "remove_accounts_from_group", "list_account_groups",
    "delete_account_group", "publish_to_group",
    "migrate_windows_profile",
]
