"""同步数据库账号快照及本地凭据到 GitHub，不输出密钥。"""

import argparse
import json
from pathlib import Path
import subprocess

from dotenv import load_dotenv


def main() -> None:
    parser = argparse.ArgumentParser(description="同步发布配置，不创建备份")
    parser.add_argument("--repository", default="xdh5/media-factory")
    args = parser.parse_args()
    root = Path(__file__).resolve().parents[2]
    load_dotenv(root / ".env")
    from core.tools.media_records import list_publishing_account_groups

    data = root / "integrations" / "media-publisher" / "data"
    path = data / "credentials.json"
    credentials = json.loads(path.read_text(encoding="utf-8"))
    accounts = list_publishing_account_groups()
    required = {row["credential_ref"] for row in accounts["members"] if row.get("credential_ref")}
    missing = required - credentials.keys()
    if missing:
        raise RuntimeError(f"缺少凭据引用：{', '.join(sorted(missing))}")
    subprocess.run(
        ["gh", "secret", "set", "PUBLISHING_CREDENTIALS_JSON", "--repo", args.repository],
        input=json.dumps(credentials, ensure_ascii=False).encode("utf-8"), check=True,
    )
    (data / "accounts.json").write_text(json.dumps(accounts, ensure_ascii=False, indent=2) + "\n", encoding="utf-8")
    print(f"已同步 {len(required)} 个凭据引用与数据库账号快照，未输出密钥")


if __name__ == "__main__":
    main()
