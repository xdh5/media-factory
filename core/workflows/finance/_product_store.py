"""把 Finance 成品索引写入项目统一 SQLite 数据库。"""

from __future__ import annotations

import json
import sqlite3
from datetime import datetime, timezone
from pathlib import Path

from ._constants import DEFAULT_DATA_ROOT
from ._errors import WorkflowStepError


def _timestamp() -> str:
    return datetime.now(timezone.utc).isoformat(timespec="seconds").replace("+00:00", "Z")


def _stored_path(value: str | Path) -> str:
    path = Path(value).resolve()
    try:
        return path.relative_to(DEFAULT_DATA_ROOT.resolve()).as_posix()
    except ValueError:
        return str(path)


def save_product(
    database_path: str | Path,
    *,
    run_id: str,
    topic_record_id: int,
    topic: str,
    title: str,
    short_title: str,
    hashtags: list[str],
    publish_copy: str,
    video_path: str | Path,
    output_dir: str | Path,
    cache_dir: str | Path,
) -> dict:
    """新增或更新一个成品索引，并返回数据库记录。"""
    database = Path(database_path).resolve()
    database.parent.mkdir(parents=True, exist_ok=True)
    created_at = _timestamp()
    try:
        connection = sqlite3.connect(database, timeout=30)
        connection.row_factory = sqlite3.Row
        try:
            connection.execute("PRAGMA journal_mode=WAL")
            connection.execute("PRAGMA foreign_keys=ON")
            connection.execute(
                """
                CREATE TABLE IF NOT EXISTS finance_products (
                    id INTEGER PRIMARY KEY AUTOINCREMENT,
                    run_id TEXT NOT NULL UNIQUE,
                    topic_record_id INTEGER NOT NULL UNIQUE,
                    topic TEXT NOT NULL,
                    title TEXT NOT NULL,
                    short_title TEXT NOT NULL,
                    hashtags_json TEXT NOT NULL,
                    publish_copy TEXT NOT NULL,
                    video_path TEXT NOT NULL,
                    output_dir TEXT NOT NULL,
                    cache_dir TEXT NOT NULL,
                    created_at TEXT NOT NULL,
                    deleted_at TEXT,
                    FOREIGN KEY(topic_record_id) REFERENCES topic_history(id)
                )
                """
            )
            existing_columns = {
                row["name"] for row in connection.execute("PRAGMA table_info(finance_products)").fetchall()
            }
            for name, declaration in (
                ("run_id", "TEXT"),
                ("cache_dir", "TEXT"),
                ("deleted_at", "TEXT"),
            ):
                if name not in existing_columns:
                    connection.execute(f"ALTER TABLE finance_products ADD COLUMN {name} {declaration}")
            connection.execute(
                "CREATE INDEX IF NOT EXISTS idx_finance_products_created_at "
                "ON finance_products(created_at DESC)"
            )
            connection.execute(
                "CREATE UNIQUE INDEX IF NOT EXISTS idx_finance_products_run_id "
                "ON finance_products(run_id) WHERE run_id IS NOT NULL"
            )
            connection.execute(
                """
                INSERT INTO finance_products(
                    run_id, topic_record_id, topic, title, short_title, hashtags_json,
                    publish_copy, video_path, output_dir, cache_dir, created_at, deleted_at
                ) VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, NULL)
                ON CONFLICT(topic_record_id) DO UPDATE SET
                    run_id=excluded.run_id,
                    topic=excluded.topic,
                    title=excluded.title,
                    short_title=excluded.short_title,
                    hashtags_json=excluded.hashtags_json,
                    publish_copy=excluded.publish_copy,
                    video_path=excluded.video_path,
                    output_dir=excluded.output_dir,
                    cache_dir=excluded.cache_dir,
                    created_at=excluded.created_at,
                    deleted_at=NULL
                """,
                (
                    run_id,
                    topic_record_id,
                    topic,
                    title,
                    short_title,
                    json.dumps(hashtags, ensure_ascii=False),
                    publish_copy,
                    _stored_path(video_path),
                    _stored_path(output_dir),
                    _stored_path(cache_dir),
                    created_at,
                ),
            )
            row = connection.execute(
                "SELECT * FROM finance_products WHERE topic_record_id=?",
                (topic_record_id,),
            ).fetchone()
            connection.commit()
        finally:
            connection.close()
    except sqlite3.Error as exc:
        raise WorkflowStepError(
            f"保存 Finance 成品索引失败：{exc}",
            {"database_path": str(database), "topic_record_id": topic_record_id},
        ) from exc
    return {
        "id": row["id"],
        "run_id": row["run_id"],
        "topic_record_id": row["topic_record_id"],
        "created_at": row["created_at"],
        "video_path": row["video_path"],
        "output_dir": row["output_dir"],
    }
