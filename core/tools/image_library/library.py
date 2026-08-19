"""按分镜从业务线图库抽图：匹配场景后在候选中随机，同一批不重复，长期均分。"""

from __future__ import annotations

import json
import random
import re
import sqlite3
from datetime import datetime, timedelta, timezone
from pathlib import Path

from ._constants import (
    DEFAULT_DATABASE_PATH,
    LINE_PATTERN,
    PROJECT_ROOT,
    TOP_CANDIDATE_COUNT,
    USAGE_WINDOW_MIN_DAYS,
)
from ._errors import ImageLibraryDatabaseError, ImageLibraryEmptyError, InvalidParameterError

__all__ = ["pick_for_shots"]


def _now() -> datetime:
    return datetime.now(timezone.utc)


def _timestamp(value: datetime) -> str:
    return value.isoformat(timespec="seconds").replace("+00:00", "Z")


def _parse_timestamp(value: str | None) -> datetime | None:
    raw = str(value or "").strip()
    if not raw:
        return None
    return datetime.fromisoformat(raw.replace("Z", "+00:00"))


def _validate_line(line: str) -> str:
    value = str(line or "").strip()
    if not re.fullmatch(LINE_PATTERN, value):
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
                tags_json TEXT NOT NULL,
                concepts_json TEXT NOT NULL,
                image_path TEXT,
                created_at TEXT NOT NULL,
                updated_at TEXT NOT NULL,
                PRIMARY KEY (line, id)
            )
            """
        )
        connection.execute(
            """
            CREATE TABLE IF NOT EXISTS image_library_picks (
                id INTEGER PRIMARY KEY AUTOINCREMENT,
                line TEXT NOT NULL,
                library_id INTEGER NOT NULL,
                shot_image_id TEXT NOT NULL,
                picked_at TEXT NOT NULL
            )
            """
        )
        connection.execute(
            "CREATE INDEX IF NOT EXISTS idx_image_library_picks_lookup "
            "ON image_library_picks(line, library_id, picked_at)"
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
        path = PROJECT_ROOT / path
    path = path.resolve()
    return path if path.is_file() else None


def _load_available(connection: sqlite3.Connection, line: str) -> list[dict]:
    rows = connection.execute(
        "SELECT id, caption, tags_json, concepts_json, image_path FROM image_library WHERE line = ? ORDER BY id",
        (line,),
    ).fetchall()
    available: list[dict] = []
    for row in rows:
        source = _resolve_image(row["image_path"])
        if source is None:
            continue
        try:
            tags = json.loads(row["tags_json"])
            concepts = json.loads(row["concepts_json"])
        except json.JSONDecodeError as exc:
            raise ImageLibraryDatabaseError(f"图库 id={row['id']} 的 tags/concepts 不是合法 JSON") from exc
        if not isinstance(tags, list) or not isinstance(concepts, list):
            raise ImageLibraryDatabaseError(f"图库 id={row['id']} 的 tags/concepts 必须是数组")
        available.append(
            {
                "library_id": int(row["id"]),
                "caption": str(row["caption"] or ""),
                "tags": [str(item).strip() for item in tags if str(item).strip()],
                "concepts": [str(item).strip() for item in concepts if str(item).strip()],
                "source_path": source.as_posix(),
            }
        )
    return available


def _cooldown_days(available_count: int, shot_count: int) -> int:
    if shot_count <= 0 or available_count <= shot_count:
        return 1
    return max(2, (available_count - shot_count) // shot_count)


def _window_days(cooldown_days: int) -> int:
    return max(USAGE_WINDOW_MIN_DAYS, cooldown_days * 3)


def _load_usage(
    connection: sqlite3.Connection,
    line: str,
    window_start: datetime,
) -> dict[int, dict]:
    usage: dict[int, dict] = {}
    rows = connection.execute(
        """
        SELECT library_id, MAX(picked_at) AS last_at, COUNT(*) AS total_count,
               SUM(CASE WHEN picked_at >= ? THEN 1 ELSE 0 END) AS window_count
        FROM image_library_picks
        WHERE line = ?
        GROUP BY library_id
        """,
        (_timestamp(window_start), line),
    ).fetchall()
    for row in rows:
        usage[int(row["library_id"])] = {
            "last_at": _parse_timestamp(row["last_at"]),
            "window_count": int(row["window_count"] or 0),
            "total_count": int(row["total_count"] or 0),
        }
    return usage


def _idle_days(item_usage: dict | None, now: datetime, window_days: int) -> int:
    last_at = None if item_usage is None else item_usage.get("last_at")
    if last_at is None:
        return window_days + 30
    delta = now - last_at
    return max(0, int(delta.total_seconds() // 86400))


def _in_cooldown(item_usage: dict | None, now: datetime, cooldown_days: int) -> bool:
    last_at = None if item_usage is None else item_usage.get("last_at")
    if last_at is None:
        return False
    return now - last_at < timedelta(days=cooldown_days)


def _score(item: dict, query: str) -> int:
    text = str(query or "")
    if not text.strip():
        return 0
    score = 0
    for tag in item["tags"]:
        if tag in text:
            score += 3
    for concept in item["concepts"]:
        if concept in text:
            score += 4
    for chunk in re.findall(r"[\u4e00-\u9fff]{2,8}", item["caption"]):
        if chunk in text:
            score += 1
    return score


def _fairness_score(item: dict, query: str, window_days: int) -> int:
    match = _score(item, query)
    idle = int(item.get("idle_days") or 0)
    window_count = int(item.get("window_count") or 0)
    return match * 5 + idle * 3 - window_count * 20 + window_days


def _choose(
    candidates: list[dict],
    query: str,
    rng: random.Random,
    now: datetime,
    usage: dict[int, dict],
    cooldown_days: int,
    window_days: int,
    remaining_slots: int,
) -> dict:
    annotated: list[dict] = []
    for item in candidates:
        stats = usage.get(item["library_id"])
        annotated.append(
            {
                **item,
                "score": _score(item, query),
                "window_count": 0 if stats is None else int(stats["window_count"]),
                "idle_days": _idle_days(stats, now, window_days),
                "cooling": _in_cooldown(stats, now, cooldown_days),
            }
        )
    cooled = [item for item in annotated if not item["cooling"]]
    pool = cooled if len(cooled) >= remaining_slots else annotated
    ranked = sorted(pool, key=lambda item: _fairness_score(item, query, window_days), reverse=True)
    shortlist = ranked[:TOP_CANDIDATE_COUNT]
    if not shortlist:
        raise ImageLibraryEmptyError("没有可抽的图库候选")
    return rng.choice(shortlist)


def _record_picks(connection: sqlite3.Connection, line: str, picks: list[dict], picked_at: str) -> None:
    connection.executemany(
        """
        INSERT INTO image_library_picks (line, library_id, shot_image_id, picked_at)
        VALUES (?, ?, ?, ?)
        """,
        [(line, item["library_id"], item["image_id"], picked_at) for item in picks],
    )
    connection.commit()


def pick_for_shots(
    line: str,
    shots: list[dict],
    *,
    exclude_library_ids: list[int] | None = None,
    database_path: str | Path | None = None,
) -> list[dict]:
    """按分镜匹配后抽取；同一批不重复，并按历史选用做冷却与长期均分。"""
    workflow = _validate_line(line)
    if not isinstance(shots, list) or not shots:
        raise InvalidParameterError("shots", "shots 必须是非空镜头列表")
    seen_image_ids: set[str] = set()
    normalized: list[tuple[str, str]] = []
    for item in shots:
        if not isinstance(item, dict):
            raise InvalidParameterError("shots", "每个镜头都必须是对象")
        image_id = str(item.get("image_id") or "").strip()
        query = str(item.get("query") or "").strip()
        if not image_id:
            raise InvalidParameterError("shots", "每个镜头都必须有 image_id")
        if image_id in seen_image_ids:
            raise InvalidParameterError("shots", f"image_id 重复：{image_id}")
        if not query:
            raise InvalidParameterError("shots", f"镜头 {image_id} 的 query 不能为空")
        seen_image_ids.add(image_id)
        normalized.append((image_id, query))
    excluded = {int(value) for value in (exclude_library_ids or [])}
    now = _now()
    connection = _connect(database_path or DEFAULT_DATABASE_PATH)
    try:
        available = _load_available(connection, workflow)
        remaining = [item for item in available if item["library_id"] not in excluded]
        if len(remaining) < len(normalized):
            raise ImageLibraryEmptyError(
                f"业务线 {workflow} 可用图只有 {len(remaining)} 张，本集需要 {len(normalized)} 张互不重复的镜头。"
                "请补图入库后再制作。",
                {"available": len(remaining), "required": len(normalized), "line": workflow},
            )
        cooldown_days = _cooldown_days(len(remaining), len(normalized))
        window_days = _window_days(cooldown_days)
        usage = _load_usage(connection, workflow, now - timedelta(days=window_days))
        rng = random.Random()
        picks: list[dict] = []
        used: set[int] = set()
        for index, (image_id, query) in enumerate(normalized):
            candidates = [item for item in remaining if item["library_id"] not in used]
            chosen = _choose(
                candidates,
                query,
                rng,
                now,
                usage,
                cooldown_days,
                window_days,
                len(normalized) - index,
            )
            used.add(chosen["library_id"])
            picks.append(
                {
                    "image_id": image_id,
                    "library_id": chosen["library_id"],
                    "caption": chosen["caption"],
                    "tags": chosen["tags"],
                    "concepts": chosen["concepts"],
                    "source_path": chosen["source_path"],
                    "score": chosen["score"],
                    "window_count": chosen["window_count"],
                    "idle_days": chosen["idle_days"],
                }
            )
        _record_picks(connection, workflow, picks, _timestamp(now))
        return picks
    finally:
        connection.close()
