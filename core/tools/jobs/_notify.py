"""用 Redis Stream 广播任务结束事件；失败时不影响 SQLite 状态。"""

from __future__ import annotations

import os

from dotenv import load_dotenv

from ._constants import JOB_EVENT_STREAM, JOB_EVENT_STREAM_MAXLEN

load_dotenv()

_TERMINAL = frozenset({"completed", "failed"})
_CLIENT = None


def _client():
    """连通则缓存连接；失败不缓存，下次再试。"""
    global _CLIENT
    if _CLIENT is not None:
        return _CLIENT
    try:
        import redis
    except ImportError:
        return None
    url = (os.environ.get("REDIS_URL") or "redis://127.0.0.1:6379/0").strip()
    try:
        client = redis.Redis.from_url(url, decode_responses=True, socket_connect_timeout=1)
        client.ping()
    except Exception:
        return None
    _CLIENT = client
    return client


def redis_available() -> bool:
    return _client() is not None


def publish_job_finished(job_id: str, workflow: str, job_type: str, status: str) -> None:
    """Worker 在 SQLite 写完终态后调用。Redis 不可用时静默跳过。"""
    if status not in _TERMINAL:
        return
    client = _client()
    if client is None:
        return
    event = "task.completed" if status == "completed" else "task.failed"
    try:
        client.xadd(
            JOB_EVENT_STREAM,
            {
                "event": event,
                "job_id": job_id,
                "workflow": workflow,
                "job_type": job_type,
                "status": status,
            },
            maxlen=JOB_EVENT_STREAM_MAXLEN,
            approximate=True,
        )
    except Exception:
        return


def _scan(messages: list, job_id: str) -> tuple[str | None, bool]:
    last_id = None
    matched = False
    for message_id, fields in messages:
        last_id = message_id
        if str(fields.get("job_id") or "") == job_id:
            matched = True
    return last_id, matched


def wait_job_event(job_id: str, *, block_ms: int, last_id: str) -> tuple[str, bool]:
    """XREAD 同一条 Stream。block_ms=0 表示不阻塞。匹配到 job_id 返回 (new_id, True)。"""
    client = _client()
    if client is None:
        return last_id, False
    kwargs = {"count": 32}
    if block_ms > 0:
        kwargs["block"] = block_ms
    try:
        payload = client.xread({JOB_EVENT_STREAM: last_id}, **kwargs)
    except Exception:
        return last_id, False
    if not payload:
        return last_id, False
    new_id = last_id
    matched = False
    for _stream, messages in payload:
        scanned_id, found = _scan(messages, job_id)
        if scanned_id:
            new_id = scanned_id
        matched = matched or found
    return new_id, matched
