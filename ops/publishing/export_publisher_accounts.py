"""Factory 将账号配置显式迁移到独立 Publisher；Publisher 不访问 Factory。"""

import json
from datetime import datetime
from shutil import copy2

from platform_api.account_registry import save_registry

from tools.database.account_groups import list_publishing_account_groups
from tools.publish_media._constants import media_publisher_root


def main() -> None:
    """保留 Publisher 已有账号及原始配置备份，不迁移凭据正文。"""
    root = media_publisher_root() / "data"
    path = root / "accounts.json"
    existing = json.loads(path.read_text(encoding="utf-8")) if path.exists() else {"groups": [], "members": []}
    incoming = list_publishing_account_groups()
    groups = {row["code"]: row for row in existing["groups"]}
    groups.update({row["code"]: row for row in incoming["groups"]})
    members = {row["account_key"]: row for row in existing["members"]}
    members.update({row["account_key"]: row for row in incoming["members"]})
    if path.exists():
        copy2(path, root / f"accounts-backup-{datetime.now():%Y%m%d%H%M%S}.json")
    result = save_registry({"groups": list(groups.values()), "members": list(members.values())}, root)
    print(json.dumps(result, ensure_ascii=False))


if __name__ == "__main__":
    main()
