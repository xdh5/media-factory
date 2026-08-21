"""从本地业务线图库列出可选图片，供宿主 Agent 按 caption 与镜头 prompt 语义匹配选图。"""

from __future__ import annotations

import re
import sqlite3
from pathlib import Path

from ._constants import IMAGE_LIBRARY_DATABASE_PATH, IMAGE_LIBRARY_LINE_PATTERN, IMAGE_LIBRARY_PROJECT_ROOT
from ._errors import ImageLibraryDatabaseError, ImageLibraryEmptyError, InvalidParameterError

__all__ = ["list_local_images"]


def _validate_line(line: str) -> str:
    value = str(line or "").strip()
    if not re.fullmatch(IMAGE_LIBRARY_LINE_PATTERN, value):
        raise InvalidParameterError("line", f"line 不合法：{line!r}")
    return value


def _connect(database_path: str | Path) -> sqlite3.Connection:
    path = Path(database_path).resolve()
    if path.suffix.lower() not in {".db", ".sqlite", ".sqlite3"}:
        raise InvalidParameterError("database_path", "数据库路径必须使用 .db、.sqlite 或 .sqlite3 扩展名")
    path.parent.mkdir(parents=True, exist_ok=True)
    try:
        connection = sqlite3.connect(path, timeout=30)
        connection.row_factory = sqlite3.Row
        connection.execute("PRAGMA journal_mode=WAL")
        connection.execute(
            """
            CREATE TABLE IF NOT EXISTS image_library (
                line TEXT NOT NULL,
                id INTEGER NOT NULL,
                caption TEXT NOT NULL,
                image_path TEXT,
                created_at TEXT NOT NULL,
                updated_at TEXT NOT NULL,
                PRIMARY KEY (line, id)
            )
            """
        )
        connection.commit()
        return connection
    except sqlite3.Error as exc:
        raise ImageLibraryDatabaseError(f"无法打开图库数据库：{path}。{exc}") from exc


def _resolve_image(image_path: str | None) -> Path | None:
    raw = str(image_path or "").strip()
    if not raw:
        return None
    path = Path(raw)
    if not path.is_absolute():
        path = IMAGE_LIBRARY_PROJECT_ROOT / path
    path = path.resolve()
    return path if path.is_file() else None


def list_local_images(
    line: str,
    *,
    database_path: str | Path | None = None,
) -> list[dict]:
    """列出业务线图库中所有可用图片（id、caption、image_path）。"""
    workflow = _validate_line(line)
    connection = _connect(database_path or IMAGE_LIBRARY_DATABASE_PATH)
    try:
        rows = connection.execute(
            "SELECT id, caption, image_path FROM image_library WHERE line = ? ORDER BY id",
            (workflow,),
        ).fetchall()
        catalog: list[dict] = []
        for row in rows:
            source = _resolve_image(row["image_path"])
            if source is None:
                continue
            catalog.append(
                {
                    "id": int(row["id"]),
                    "caption": str(row["caption"] or ""),
                    "image_path": str(row["image_path"] or "").strip(),
                }
            )
        if not catalog:
            raise ImageLibraryEmptyError(
                f"业务线 {workflow} 图库为空或图片文件均不存在，请先补图入库后再制作。",
                {"line": workflow},
            )
        return catalog
    finally:
        connection.close()
