"""MatrixMedia 账号登记、账号组和按组发布能力。"""

from __future__ import annotations

import sqlite3
import os
import shutil
from datetime import datetime, timezone
from pathlib import Path
from urllib.parse import unquote

from ._constants import (
    MATRIXMEDIA_USER_DATA_ROOT,
    PLATFORM_IDS_BY_NAME,
    PLATFORM_NAMES,
    PROJECT_DATABASE_PATH,
    QUERY_PLATFORMS,
)
from ._errors import (
    AccountDatabaseError,
    AccountGroupNotFoundError,
    AccountNotFoundError,
    InvalidParameterError,
    MatrixMediaToolError,
)

__all__ = [
    "register_account",
    "list_registered_accounts",
    "create_account_group",
    "add_accounts_to_group",
    "remove_accounts_from_group",
    "list_account_groups",
    "delete_account_group",
    "publish_to_group",
    "migrate_windows_profile",
]


def _timestamp() -> str:
    return datetime.now(timezone.utc).isoformat(timespec="seconds").replace("+00:00", "Z")


def _text(value: str | None, parameter: str, *, required: bool = True) -> str | None:
    if value is None and not required:
        return None
    if not isinstance(value, str) or not value.strip():
        raise InvalidParameterError(parameter, f"{parameter} 必须是非空字符串")
    return value.strip()


def _connect(database_path: str | Path | None = None) -> sqlite3.Connection:
    database = Path(database_path or PROJECT_DATABASE_PATH).resolve()
    database.parent.mkdir(parents=True, exist_ok=True)
    try:
        connection = sqlite3.connect(database, timeout=30)
        connection.row_factory = sqlite3.Row
        connection.execute("PRAGMA journal_mode=WAL")
        connection.execute("PRAGMA foreign_keys=ON")
        connection.executescript(
            """
            CREATE TABLE IF NOT EXISTS matrixmedia_accounts (
                id INTEGER PRIMARY KEY AUTOINCREMENT,
                platform TEXT NOT NULL,
                phone TEXT,
                partition TEXT NOT NULL UNIQUE,
                alias TEXT,
                created_at TEXT NOT NULL,
                updated_at TEXT NOT NULL
            );
            CREATE TABLE IF NOT EXISTS matrixmedia_account_groups (
                id INTEGER PRIMARY KEY AUTOINCREMENT,
                name TEXT NOT NULL UNIQUE,
                created_at TEXT NOT NULL,
                updated_at TEXT NOT NULL
            );
            CREATE TABLE IF NOT EXISTS matrixmedia_account_group_members (
                group_id INTEGER NOT NULL,
                account_id INTEGER NOT NULL,
                created_at TEXT NOT NULL,
                PRIMARY KEY(group_id, account_id),
                FOREIGN KEY(group_id) REFERENCES matrixmedia_account_groups(id) ON DELETE CASCADE,
                FOREIGN KEY(account_id) REFERENCES matrixmedia_accounts(id) ON DELETE CASCADE
            );
            """
        )
        connection.commit()
        return connection
    except sqlite3.Error as exc:
        raise AccountDatabaseError(
            f"初始化 MatrixMedia 账号数据库失败：{exc}",
            {"database_path": str(database)},
        ) from exc


def _account(row: sqlite3.Row) -> dict:
    return {key: row[key] for key in ("id", "platform", "phone", "partition", "alias", "created_at", "updated_at")}


def _group(connection: sqlite3.Connection, group_id: int) -> dict:
    row = connection.execute("SELECT * FROM matrixmedia_account_groups WHERE id=?", (group_id,)).fetchone()
    if row is None:
        raise AccountGroupNotFoundError(f"没有找到账号组 id={group_id}", {"group_id": group_id})
    members = connection.execute(
        """
        SELECT a.* FROM matrixmedia_accounts a
        JOIN matrixmedia_account_group_members m ON m.account_id=a.id
        WHERE m.group_id=? ORDER BY a.id
        """,
        (group_id,),
    ).fetchall()
    return {
        "id": row["id"],
        "name": row["name"],
        "created_at": row["created_at"],
        "updated_at": row["updated_at"],
        "accounts": [_account(member) for member in members],
    }


def _validate_ids(connection: sqlite3.Connection, account_ids: list[int]) -> list[int]:
    if not isinstance(account_ids, list) or any(
        isinstance(item, bool) or not isinstance(item, int) or item < 1 for item in account_ids
    ):
        raise InvalidParameterError("account_ids", "account_ids 必须是正整数列表")
    identifiers = list(dict.fromkeys(account_ids))
    if not identifiers:
        return []
    placeholders = ",".join("?" for _ in identifiers)
    found = {
        row["id"] for row in connection.execute(
            f"SELECT id FROM matrixmedia_accounts WHERE id IN ({placeholders})",
            identifiers,
        ).fetchall()
    }
    missing = [item for item in identifiers if item not in found]
    if missing:
        raise AccountNotFoundError(f"账号不存在：{missing}", {"account_ids": missing})
    return identifiers


def register_account(
    platform: str,
    *,
    phone: str | None = None,
    partition: str | None = None,
    alias: str | None = None,
    database_path: str | Path | None = None,
) -> dict:
    """登记一个可供账号组使用的 MatrixMedia 登录分区。"""
    if platform not in QUERY_PLATFORMS:
        raise InvalidParameterError("platform", f"platform 必须从 {QUERY_PLATFORMS} 中选择")
    if bool(phone) == bool(partition):
        raise InvalidParameterError("phone/partition", "phone 和 partition 必须且只能传入一个")
    normalized_phone = _text(phone, "phone") if phone else None
    normalized_partition = _text(partition, "partition") if partition else (
        f"persist:{normalized_phone.split('-')[0]}{PLATFORM_NAMES[platform]}"
    )
    normalized_alias = _text(alias, "alias", required=False)
    timestamp = _timestamp()
    connection = _connect(database_path)
    try:
        connection.execute(
            """
            INSERT INTO matrixmedia_accounts(platform, phone, partition, alias, created_at, updated_at)
            VALUES (?, ?, ?, ?, ?, ?)
            ON CONFLICT(partition) DO UPDATE SET
                platform=excluded.platform,
                phone=COALESCE(excluded.phone, matrixmedia_accounts.phone),
                alias=COALESCE(excluded.alias, matrixmedia_accounts.alias),
                updated_at=excluded.updated_at
            """,
            (platform, normalized_phone, normalized_partition, normalized_alias, timestamp, timestamp),
        )
        row = connection.execute(
            "SELECT * FROM matrixmedia_accounts WHERE partition=?",
            (normalized_partition,),
        ).fetchone()
        connection.commit()
        return _account(row)
    except sqlite3.Error as exc:
        connection.rollback()
        raise AccountDatabaseError(f"登记 MatrixMedia 账号失败：{exc}") from exc
    finally:
        connection.close()


def list_registered_accounts(database_path: str | Path | None = None) -> list[dict]:
    connection = _connect(database_path)
    try:
        return [_account(row) for row in connection.execute("SELECT * FROM matrixmedia_accounts ORDER BY id")]
    finally:
        connection.close()


def create_account_group(
    name: str,
    account_ids: list[int] | None = None,
    database_path: str | Path | None = None,
) -> dict:
    normalized_name = _text(name, "name")
    connection = _connect(database_path)
    try:
        identifiers = _validate_ids(connection, account_ids or [])
        timestamp = _timestamp()
        cursor = connection.execute(
            "INSERT INTO matrixmedia_account_groups(name, created_at, updated_at) VALUES (?, ?, ?)",
            (normalized_name, timestamp, timestamp),
        )
        for account_id in identifiers:
            connection.execute(
                "INSERT INTO matrixmedia_account_group_members(group_id, account_id, created_at) VALUES (?, ?, ?)",
                (cursor.lastrowid, account_id, timestamp),
            )
        connection.commit()
        return _group(connection, cursor.lastrowid)
    except sqlite3.IntegrityError as exc:
        connection.rollback()
        raise InvalidParameterError("name", f"账号组名称已经存在：{normalized_name}") from exc
    finally:
        connection.close()


def _change_members(
    group_id: int,
    account_ids: list[int],
    *,
    add: bool,
    database_path: str | Path | None,
) -> dict:
    connection = _connect(database_path)
    try:
        _group(connection, group_id)
        identifiers = _validate_ids(connection, account_ids)
        timestamp = _timestamp()
        for account_id in identifiers:
            if add:
                connection.execute(
                    "INSERT OR IGNORE INTO matrixmedia_account_group_members(group_id, account_id, created_at) "
                    "VALUES (?, ?, ?)",
                    (group_id, account_id, timestamp),
                )
            else:
                connection.execute(
                    "DELETE FROM matrixmedia_account_group_members WHERE group_id=? AND account_id=?",
                    (group_id, account_id),
                )
        connection.execute(
            "UPDATE matrixmedia_account_groups SET updated_at=? WHERE id=?",
            (timestamp, group_id),
        )
        connection.commit()
        return _group(connection, group_id)
    finally:
        connection.close()


def add_accounts_to_group(
    group_id: int,
    account_ids: list[int],
    database_path: str | Path | None = None,
) -> dict:
    return _change_members(group_id, account_ids, add=True, database_path=database_path)


def remove_accounts_from_group(
    group_id: int,
    account_ids: list[int],
    database_path: str | Path | None = None,
) -> dict:
    return _change_members(group_id, account_ids, add=False, database_path=database_path)


def list_account_groups(database_path: str | Path | None = None) -> list[dict]:
    connection = _connect(database_path)
    try:
        identifiers = [row["id"] for row in connection.execute("SELECT id FROM matrixmedia_account_groups ORDER BY id")]
        return [_group(connection, identifier) for identifier in identifiers]
    finally:
        connection.close()


def delete_account_group(group_id: int, database_path: str | Path | None = None) -> dict:
    connection = _connect(database_path)
    try:
        group = _group(connection, group_id)
        connection.execute("DELETE FROM matrixmedia_account_groups WHERE id=?", (group_id,))
        connection.commit()
        return {"id": group_id, "name": group["name"], "deleted": True}
    finally:
        connection.close()


def publish_to_group(
    group_id: int,
    video_path: str | Path,
    title: str,
    *,
    short_title: str | None = None,
    tags: list[str] | None = None,
    task_name: str | None = None,
    address: str | None = None,
    publish_at: str | None = None,
    draft: bool = False,
    database_path: str | Path | None = None,
) -> dict:
    """按账号组顺序逐账号发布；单个账号失败不会阻断后续账号。"""
    connection = _connect(database_path)
    try:
        group = _group(connection, group_id)
    finally:
        connection.close()
    if not group["accounts"]:
        raise InvalidParameterError("group_id", f"账号组“{group['name']}”没有成员")
    results = []
    for account in group["accounts"]:
        try:
            from .matrixmedia_cli import publish_video

            result = publish_video(
                account["platform"],
                video_path,
                title,
                partition=account["partition"],
                short_title=short_title,
                tags=tags,
                task_name=task_name,
                address=address,
                publish_at=publish_at,
                draft=draft,
            )
            results.append({"account": account, "success": True, "result": result})
        except MatrixMediaToolError as exc:
            results.append({"account": account, "success": False, "error": exc.to_dict()["error"]})
    return {
        "group_id": group_id,
        "group_name": group["name"],
        "success": all(item["success"] for item in results),
        "results": results,
    }


def _default_windows_user_data() -> Path:
    app_data = os.getenv("APPDATA", "").strip()
    if not app_data:
        raise InvalidParameterError(
            "source_user_data",
            "当前环境没有 APPDATA，必须显式传入 MatrixMedia userData 路径",
        )
    return Path(app_data) / "matrix-video"


def _copy_profile(source: Path, target: Path) -> int:
    if not source.is_dir():
        raise InvalidParameterError("source_user_data", f"MatrixMedia userData 目录不存在：{source}")
    target.mkdir(parents=True, exist_ok=True)
    copied = 0
    local_state = source / "Local State"
    if local_state.is_file():
        shutil.copy2(local_state, target / "Local State")
        copied += 1
    source_partitions = source / "Partitions"
    target_partitions = target / "Partitions"
    if source_partitions.is_dir():
        before = {path.relative_to(target) for path in target.rglob("*") if path.is_file()}
        shutil.copytree(
            source_partitions,
            target_partitions,
            dirs_exist_ok=True,
            ignore=shutil.ignore_patterns(
                "LOCK", "lockfile", "Cache", "Code Cache", "GPUCache", "DawnCache",
                "Service Worker", "Session Storage", "blob_storage", "VideoDecodeStats",
            ),
        )
        after = {path.relative_to(target) for path in target.rglob("*") if path.is_file()}
        copied += len(after - before)
    return copied


def _partition_accounts(partitions_root: Path, database_path: str | Path | None) -> list[dict]:
    accounts = []
    if not partitions_root.is_dir():
        return accounts
    platform_names = sorted(PLATFORM_IDS_BY_NAME, key=len, reverse=True)
    for directory in sorted(path for path in partitions_root.iterdir() if path.is_dir()):
        decoded = unquote(directory.name)
        platform_name = next((name for name in platform_names if decoded.endswith(name)), None)
        if platform_name is None:
            continue
        group_name = decoded[:-len(platform_name)].strip()
        if not group_name:
            continue
        account = register_account(
            PLATFORM_IDS_BY_NAME[platform_name],
            partition=f"persist:{decoded}",
            alias=group_name,
            database_path=database_path,
        )
        account["group_name"] = group_name
        accounts.append(account)
    return accounts


def migrate_windows_profile(
    source_user_data: str | Path | None = None,
    database_path: str | Path | None = None,
) -> dict:
    """复制本机 Cookie 分区，并把分区对应账号组登记到统一数据库。"""
    source = Path(source_user_data).resolve() if source_user_data else _default_windows_user_data().resolve()
    target = MATRIXMEDIA_USER_DATA_ROOT.resolve()
    if source == target:
        raise InvalidParameterError("source_user_data", "源 userData 与项目目标目录不能相同")
    try:
        copied_files = _copy_profile(source, target)
    except OSError as exc:
        raise AccountDatabaseError(
            f"迁移 MatrixMedia Cookie 文件失败：{exc}。请关闭正在运行的 MatrixMedia 后重试",
            {"source_user_data": str(source), "target_user_data": str(target)},
        ) from exc
    accounts = _partition_accounts(target / "Partitions", database_path)
    grouped: dict[str, list[int]] = {}
    for account in accounts:
        grouped.setdefault(account.pop("group_name"), []).append(account["id"])
    connection = _connect(database_path)
    try:
        timestamp = _timestamp()
        for name, account_ids in grouped.items():
            row = connection.execute(
                "SELECT id FROM matrixmedia_account_groups WHERE name=?",
                (name,),
            ).fetchone()
            if row is None:
                cursor = connection.execute(
                    "INSERT INTO matrixmedia_account_groups(name, created_at, updated_at) VALUES (?, ?, ?)",
                    (name, timestamp, timestamp),
                )
                group_id = cursor.lastrowid
            else:
                group_id = row["id"]
            for account_id in account_ids:
                connection.execute(
                    "INSERT OR IGNORE INTO matrixmedia_account_group_members(group_id, account_id, created_at) "
                    "VALUES (?, ?, ?)",
                    (group_id, account_id, timestamp),
                )
            connection.execute(
                "UPDATE matrixmedia_account_groups SET updated_at=? WHERE id=?",
                (timestamp, group_id),
            )
        connection.commit()
    finally:
        connection.close()
    return {
        "source_user_data": str(source),
        "target_user_data": str(target),
        "copied_files": copied_files,
        "accounts": accounts,
        "groups": list_account_groups(database_path),
    }
