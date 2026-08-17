"""安全删除 Finance 单条成品或缓存。"""

from __future__ import annotations

import re
import shutil
import sqlite3
from datetime import datetime, timezone
from pathlib import Path

from ._constants import DEFAULT_CACHE_ROOT, DEFAULT_DATABASE_PATH, DEFAULT_DATA_ROOT, DEFAULT_OUTPUT_ROOT
from ._errors import ProductDeletionError, ProductNotFoundError

__all__ = ["delete_finance_product", "delete_finance_cache"]


def _timestamp() -> str:
    return datetime.now(timezone.utc).isoformat(timespec="seconds").replace("+00:00", "Z")


def _record(database: Path, product_record_id: int) -> dict:
    if isinstance(product_record_id, bool) or not isinstance(product_record_id, int) or product_record_id < 1:
        raise ProductDeletionError("product_record_id 必须是大于等于 1 的整数")
    try:
        connection = sqlite3.connect(database, timeout=30)
        connection.row_factory = sqlite3.Row
        try:
            row = connection.execute(
                "SELECT * FROM finance_products WHERE id=?",
                (product_record_id,),
            ).fetchone()
        finally:
            connection.close()
    except sqlite3.Error as exc:
        raise ProductDeletionError(
            f"读取成品记录失败：{exc}",
            {"database_path": str(database), "product_record_id": product_record_id},
        ) from exc
    if row is None:
        raise ProductNotFoundError(
            f"没有找到 Finance 成品记录 id={product_record_id}",
            {"product_record_id": product_record_id},
        )
    return dict(row)


def _safe_directory(stored_path: str, expected_root: Path, run_id: str, field: str) -> Path:
    if not re.fullmatch(r"run-\d{6,}", str(run_id or "")):
        raise ProductDeletionError(f"数据库中的 run_id 不安全：{run_id}", {"field": "run_id"})
    value = Path(stored_path)
    resolved = value.resolve() if value.is_absolute() else (DEFAULT_DATA_ROOT / value).resolve()
    expected = (expected_root / run_id).resolve()
    if resolved != expected:
        raise ProductDeletionError(
            f"拒绝删除：数据库中的 {field} 不等于该成品的标准目录",
            {"stored_path": stored_path, "expected_path": str(expected)},
        )
    return resolved


def _remove_directory(path: Path) -> bool:
    if not path.exists():
        return False
    if not path.is_dir():
        raise ProductDeletionError(f"拒绝删除：目标不是目录：{path}")
    shutil.rmtree(path)
    return True


def delete_finance_cache(
    product_record_id: int,
    database_path: str | Path | None = None,
) -> dict:
    """只删除单条成品的缓存，保留成品文件和数据库记录。"""
    database = Path(database_path or DEFAULT_DATABASE_PATH).resolve()
    record = _record(database, product_record_id)
    cache_dir = _safe_directory(record["cache_dir"], DEFAULT_CACHE_ROOT, record["run_id"], "cache_dir")
    return {
        "product_record_id": product_record_id,
        "run_id": record["run_id"],
        "output_deleted": False,
        "cache_deleted": _remove_directory(cache_dir),
        "deleted_at": record.get("deleted_at"),
    }


def delete_finance_product(
    product_record_id: int,
    *,
    delete_cache: bool = True,
    database_path: str | Path | None = None,
) -> dict:
    """删除成品目录并软删除数据库记录，可同时删除对应缓存。"""
    if not isinstance(delete_cache, bool):
        raise ProductDeletionError("delete_cache 必须是布尔值")
    database = Path(database_path or DEFAULT_DATABASE_PATH).resolve()
    record = _record(database, product_record_id)
    output_dir = _safe_directory(record["output_dir"], DEFAULT_OUTPUT_ROOT, record["run_id"], "output_dir")
    cache_dir = _safe_directory(record["cache_dir"], DEFAULT_CACHE_ROOT, record["run_id"], "cache_dir")
    output_deleted = _remove_directory(output_dir)
    cache_deleted = _remove_directory(cache_dir) if delete_cache else False
    deleted_at = _timestamp()
    try:
        connection = sqlite3.connect(database, timeout=30)
        try:
            connection.execute(
                "UPDATE finance_products SET deleted_at=? WHERE id=?",
                (deleted_at, product_record_id),
            )
            connection.commit()
        finally:
            connection.close()
    except sqlite3.Error as exc:
        raise ProductDeletionError(
            f"成品文件已处理，但写入软删除时间失败：{exc}",
            {"database_path": str(database), "product_record_id": product_record_id},
        ) from exc
    return {
        "product_record_id": product_record_id,
        "run_id": record["run_id"],
        "output_deleted": output_deleted,
        "cache_deleted": cache_deleted,
        "deleted_at": deleted_at,
    }
