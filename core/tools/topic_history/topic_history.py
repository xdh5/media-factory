"""使用 SQLite 保存工作流话题并执行时间窗口去重。"""

from __future__ import annotations

import hashlib
import re
import sqlite3
import unicodedata
from datetime import datetime, timedelta, timezone
from pathlib import Path

from ._constants import ACTIVE_TOPIC_STATUSES, DEFAULT_DEDUPLICATION_DAYS, SUPPORTED_TOPIC_STATUSES
from ._errors import (
    DuplicateTopicError,
    InvalidParameterError,
    TopicDatabaseError,
    TopicRecordNotFoundError,
)

__all__ = ["recent_topics", "reserve_topic", "update_topic_status"]


def _now() -> datetime:
    return datetime.now(timezone.utc)


def _timestamp(value: datetime) -> str:
    return value.isoformat(timespec="seconds").replace("+00:00", "Z")


def _validate_text(value: str, parameter: str) -> str:
    if not isinstance(value, str) or not value.strip():
        raise InvalidParameterError(parameter, f"{parameter} 必须是非空字符串")
    return value.strip()


def _validate_days(days: int) -> int:
    if isinstance(days, bool) or not isinstance(days, int) or days < 1:
        raise InvalidParameterError("days", "days 必须是大于等于 1 的整数")
    return days


def _fingerprint(topic: str) -> str:
    normalized = unicodedata.normalize("NFKC", topic).lower()
    normalized = re.sub(r"[^\w\u4e00-\u9fff]+", "", normalized)
    if not normalized:
        raise InvalidParameterError("topic", "topic 规范化后为空，请提供包含文字或数字的话题")
    return hashlib.sha256(normalized.encode("utf-8")).hexdigest()


def _connect(database_path: str | Path) -> sqlite3.Connection:
    path = Path(database_path).resolve()
    if path.suffix.lower() not in {".db", ".sqlite", ".sqlite3"}:
        raise InvalidParameterError("database_path", "数据库路径必须使用 .db、.sqlite 或 .sqlite3 扩展名")
    path.parent.mkdir(parents=True, exist_ok=True)
    try:
        connection = sqlite3.connect(path, timeout=30)
        connection.row_factory = sqlite3.Row
        connection.execute("PRAGMA journal_mode=WAL")
        connection.execute("PRAGMA foreign_keys=ON")
        connection.execute(
            """
            CREATE TABLE IF NOT EXISTS topic_history (
                id INTEGER PRIMARY KEY AUTOINCREMENT,
                workflow TEXT NOT NULL,
                topic TEXT NOT NULL,
                fingerprint TEXT NOT NULL,
                status TEXT NOT NULL,
                created_at TEXT NOT NULL,
                updated_at TEXT NOT NULL
            )
            """
        )
        connection.execute(
            "CREATE INDEX IF NOT EXISTS idx_topic_history_lookup "
            "ON topic_history(workflow, fingerprint, created_at, status)"
        )
        connection.commit()
        return connection
    except sqlite3.Error as exc:
        raise TopicDatabaseError(f"无法初始化话题数据库：{path}。{exc}") from exc


def _record(row: sqlite3.Row) -> dict:
    return {key: row[key] for key in ("id", "workflow", "topic", "fingerprint", "status", "created_at", "updated_at")}


def recent_topics(
    database_path: str | Path,
    workflow: str,
    days: int = DEFAULT_DEDUPLICATION_DAYS,
) -> list[dict]:
    """返回指定工作流在时间窗口内已占用的话题。"""
    normalized_workflow = _validate_text(workflow, "workflow")
    window_days = _validate_days(days)
    cutoff = _timestamp(_now() - timedelta(days=window_days))
    placeholders = ",".join("?" for _ in ACTIVE_TOPIC_STATUSES)
    try:
        connection = _connect(database_path)
        try:
            rows = connection.execute(
                f"SELECT * FROM topic_history WHERE workflow=? AND created_at>=? "
                f"AND status IN ({placeholders}) ORDER BY created_at DESC",
                (normalized_workflow, cutoff, *ACTIVE_TOPIC_STATUSES),
            ).fetchall()
            return [_record(row) for row in rows]
        finally:
            connection.close()
    except sqlite3.Error as exc:
        raise TopicDatabaseError(f"读取最近话题失败：{exc}") from exc


def reserve_topic(
    database_path: str | Path,
    workflow: str,
    topic: str,
    days: int = DEFAULT_DEDUPLICATION_DAYS,
) -> dict:
    """原子检查时间窗口并占用话题，防止并发工作流重复生成。"""
    normalized_workflow = _validate_text(workflow, "workflow")
    normalized_topic = _validate_text(topic, "topic")
    window_days = _validate_days(days)
    fingerprint = _fingerprint(normalized_topic)
    now = _now()
    cutoff = _timestamp(now - timedelta(days=window_days))
    placeholders = ",".join("?" for _ in ACTIVE_TOPIC_STATUSES)
    try:
        connection = _connect(database_path)
        try:
            connection.execute("BEGIN IMMEDIATE")
            duplicate = connection.execute(
                f"SELECT * FROM topic_history WHERE workflow=? AND fingerprint=? AND created_at>=? "
                f"AND status IN ({placeholders}) ORDER BY created_at DESC LIMIT 1",
                (normalized_workflow, fingerprint, cutoff, *ACTIVE_TOPIC_STATUSES),
            ).fetchone()
            if duplicate:
                raise DuplicateTopicError(
                    f"话题在最近 {window_days} 天内已经使用：{duplicate['topic']}",
                    {"duplicate_record": _record(duplicate), "days": window_days},
                )
            timestamp = _timestamp(now)
            cursor = connection.execute(
                "INSERT INTO topic_history(workflow, topic, fingerprint, status, created_at, updated_at) "
                "VALUES (?, ?, ?, 'reserved', ?, ?)",
                (normalized_workflow, normalized_topic, fingerprint, timestamp, timestamp),
            )
            row = connection.execute("SELECT * FROM topic_history WHERE id=?", (cursor.lastrowid,)).fetchone()
            connection.commit()
            return _record(row)
        except Exception:
            connection.rollback()
            raise
        finally:
            connection.close()
    except DuplicateTopicError:
        raise
    except sqlite3.Error as exc:
        raise TopicDatabaseError(f"占用话题失败：{exc}") from exc


def update_topic_status(database_path: str | Path, record_id: int, status: str) -> dict:
    """更新话题状态；工作流失败时标为 failed，可重新选用。"""
    if isinstance(record_id, bool) or not isinstance(record_id, int) or record_id < 1:
        raise InvalidParameterError("record_id", "record_id 必须是大于等于 1 的整数")
    if status not in SUPPORTED_TOPIC_STATUSES:
        raise InvalidParameterError("status", f"status 必须从 {SUPPORTED_TOPIC_STATUSES} 中选择")
    try:
        connection = _connect(database_path)
        try:
            cursor = connection.execute(
                "UPDATE topic_history SET status=?, updated_at=? WHERE id=?",
                (status, _timestamp(_now()), record_id),
            )
            if cursor.rowcount != 1:
                raise TopicRecordNotFoundError(
                    f"没有找到话题记录 id={record_id}",
                    {"record_id": record_id},
                )
            row = connection.execute("SELECT * FROM topic_history WHERE id=?", (record_id,)).fetchone()
            connection.commit()
            return _record(row)
        finally:
            connection.close()
    except TopicRecordNotFoundError:
        raise
    except sqlite3.Error as exc:
        raise TopicDatabaseError(f"更新话题状态失败：{exc}") from exc
