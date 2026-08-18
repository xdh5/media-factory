"""跨工作流的后台任务：入库、独立进程执行、按 job_id 查询。"""

from __future__ import annotations

import hashlib
import importlib
import json
import os
import queue
import re
import sqlite3
import subprocess
import sys
import threading
from datetime import datetime, timezone
from pathlib import Path
from uuid import uuid4

from ._constants import (
    DEFAULT_DATABASE_PATH,
    HANDLER_PATTERN,
    JOB_HEARTBEAT_SECONDS,
    JOB_ID_PATTERN,
    JOB_SCHEMA_VERSION,
    PROCESS_MODULE,
    PROJECT_ROOT,
    WORKFLOW_ID_PATTERN,
)
from ._errors import InvalidParameterError, JobExecutionError, JobNotFoundError

_QUEUE: queue.Queue[tuple[str, Path]] = queue.Queue()
_WORKER_LOCK = threading.Lock()
_WORKER_STARTED = False


def _timestamp() -> str:
    return datetime.now(timezone.utc).isoformat(timespec="seconds").replace("+00:00", "Z")


def _workflow_id(workflow: str) -> str:
    value = str(workflow or "").strip()
    if not re.fullmatch(WORKFLOW_ID_PATTERN, value):
        raise InvalidParameterError("workflow", f"workflow 不合法：{workflow!r}")
    return value


def _handler(handler: str) -> str:
    value = str(handler or "").strip()
    if not re.fullmatch(HANDLER_PATTERN, value):
        raise InvalidParameterError(
            "handler",
            f"handler 必须是 module.path:function，当前为 {handler!r}",
        )
    return value


def _connect(database_path: str | Path) -> sqlite3.Connection:
    path = Path(database_path).resolve()
    path.parent.mkdir(parents=True, exist_ok=True)
    connection = sqlite3.connect(path, timeout=30)
    connection.row_factory = sqlite3.Row
    connection.execute("PRAGMA journal_mode=WAL")
    connection.execute(
        """
        CREATE TABLE IF NOT EXISTS workflow_jobs (
            job_id TEXT PRIMARY KEY,
            workflow TEXT NOT NULL,
            job_type TEXT NOT NULL,
            handler TEXT NOT NULL,
            request_key TEXT NOT NULL,
            status TEXT NOT NULL,
            progress_message TEXT NOT NULL,
            input_json TEXT NOT NULL,
            result_json TEXT,
            error_json TEXT,
            created_at TEXT NOT NULL,
            started_at TEXT,
            finished_at TEXT,
            updated_at TEXT NOT NULL,
            schema_version INTEGER NOT NULL
        )
        """
    )
    connection.execute(
        "CREATE INDEX IF NOT EXISTS idx_workflow_jobs_request "
        "ON workflow_jobs(workflow, job_type, request_key, status, created_at)"
    )
    connection.commit()
    return connection


def _decode(row: sqlite3.Row) -> dict:
    return {
        "job_id": row["job_id"],
        "workflow": row["workflow"],
        "job_type": row["job_type"],
        "status": row["status"],
        "progress_message": row["progress_message"],
        "result": json.loads(row["result_json"]) if row["result_json"] else None,
        "error": json.loads(row["error_json"]) if row["error_json"] else None,
        "created_at": row["created_at"],
        "started_at": row["started_at"],
        "finished_at": row["finished_at"],
        "updated_at": row["updated_at"],
    }


def _request_key(workflow: str, job_type: str, payload: dict) -> str:
    encoded = json.dumps(
        {"workflow": workflow, "job_type": job_type, "payload": payload},
        ensure_ascii=False,
        sort_keys=True,
        separators=(",", ":"),
    ).encode("utf-8")
    return hashlib.sha256(encoded).hexdigest()


def _error_payload(exc: Exception) -> dict:
    if hasattr(exc, "to_dict"):
        converted = exc.to_dict()
        if isinstance(converted, dict) and isinstance(converted.get("error"), dict):
            return converted["error"]
    return {
        "code": "JOB_EXECUTION_ERROR",
        "message": f"后台任务执行失败：{type(exc).__name__}: {exc}",
        "details": {"exception_type": type(exc).__name__},
    }


def _update(
    database_path: Path,
    job_id: str,
    *,
    status: str,
    progress_message: str,
    result: dict | None = None,
    error: dict | None = None,
) -> None:
    now = _timestamp()
    started_at = now if status == "running" else None
    finished_at = now if status in {"completed", "failed"} else None
    connection = _connect(database_path)
    try:
        connection.execute(
            "UPDATE workflow_jobs SET status=?, progress_message=?, result_json=?, error_json=?, "
            "started_at=COALESCE(started_at, ?), finished_at=?, updated_at=? WHERE job_id=?",
            (
                status,
                progress_message,
                json.dumps(result, ensure_ascii=False) if result is not None else None,
                json.dumps(error, ensure_ascii=False) if error is not None else None,
                started_at,
                finished_at,
                now,
                job_id,
            ),
        )
        connection.commit()
    finally:
        connection.close()


def _heartbeat(database_path: Path, job_id: str, stop_event: threading.Event) -> None:
    while not stop_event.wait(JOB_HEARTBEAT_SECONDS):
        connection = None
        try:
            connection = _connect(database_path)
            connection.execute(
                "UPDATE workflow_jobs SET updated_at=? WHERE job_id=? AND status='running'",
                (_timestamp(), job_id),
            )
            connection.commit()
        except sqlite3.Error:
            pass
        finally:
            if connection is not None:
                connection.close()


def _worker() -> None:
    while True:
        job_id, database_path = _QUEUE.get()
        try:
            environment = os.environ.copy()
            existing_pythonpath = environment.get("PYTHONPATH", "")
            environment["PYTHONPATH"] = os.pathsep.join(
                value for value in (str(PROJECT_ROOT), existing_pythonpath) if value
            )
            completed = subprocess.run(
                [
                    sys.executable,
                    "-m",
                    PROCESS_MODULE,
                    str(database_path),
                    job_id,
                ],
                cwd=PROJECT_ROOT,
                env=environment,
                check=False,
                capture_output=True,
                text=True,
                encoding="utf-8",
                errors="replace",
            )
            current = get_job(job_id, database_path=database_path)
            if completed.returncode != 0 and current["status"] not in {"completed", "failed"}:
                details = (completed.stderr or completed.stdout or "").strip()[-3000:]
                raise JobExecutionError(
                    f"独立任务进程异常退出（退出码 {completed.returncode}）：{details or '没有错误输出'}"
                )
        except Exception as exc:
            current = get_job(job_id, database_path=database_path)
            if current["status"] not in {"completed", "failed"}:
                _update(
                    database_path,
                    job_id,
                    status="failed",
                    progress_message="任务执行失败，请查看 error 并修正后重试",
                    error=_error_payload(exc),
                )
        finally:
            _QUEUE.task_done()


def execute_persisted_job(database_path: str | Path, job_id: str) -> None:
    """在独立解释器中读取任务并调用工作流登记的 handler。"""
    database = Path(database_path).resolve()
    connection = _connect(database)
    try:
        row = connection.execute(
            "SELECT job_type, handler, input_json, status FROM workflow_jobs WHERE job_id=?",
            (job_id,),
        ).fetchone()
    finally:
        connection.close()
    if row is None:
        raise JobNotFoundError(f"没有找到后台任务：{job_id}", {"job_id": job_id})
    if row["status"] not in {"queued", "running"}:
        return
    try:
        payload = json.loads(row["input_json"])
    except json.JSONDecodeError as exc:
        raise JobExecutionError(f"后台任务输入不是有效 JSON：{job_id}") from exc

    _update(database, job_id, status="running", progress_message="任务正在独立进程中执行")
    heartbeat_stop = threading.Event()
    heartbeat_thread = threading.Thread(
        target=_heartbeat,
        args=(database, job_id, heartbeat_stop),
        name=f"job-heartbeat-{job_id[-8:]}",
        daemon=True,
    )
    heartbeat_thread.start()
    try:
        module_name, function_name = str(row["handler"]).split(":", 1)
        function = getattr(importlib.import_module(module_name), function_name)
        result = function(row["job_type"], payload)
        if not isinstance(result, dict):
            raise JobExecutionError("后台任务 handler 必须返回对象")
        _update(database, job_id, status="completed", progress_message="任务已完成", result=result)
    except Exception as exc:
        _update(
            database,
            job_id,
            status="failed",
            progress_message="任务执行失败，请查看 error 并修正后重试",
            error=_error_payload(exc),
        )
    finally:
        heartbeat_stop.set()
        heartbeat_thread.join(timeout=1)


def _ensure_worker() -> None:
    global _WORKER_STARTED
    with _WORKER_LOCK:
        if _WORKER_STARTED:
            return
        threading.Thread(target=_worker, name="workflow-job-worker", daemon=True).start()
        _WORKER_STARTED = True


def recover_interrupted_jobs(workflow: str, database_path: str | Path | None = None) -> None:
    """把该工作流上次退出时仍排队或运行的任务标为失败。"""
    workflow_id = _workflow_id(workflow)
    database = Path(database_path or DEFAULT_DATABASE_PATH).resolve()
    connection = _connect(database)
    try:
        now = _timestamp()
        error = {
            "code": "JOB_INTERRUPTED",
            "message": "MCP 服务在任务完成前退出；已有缓存会保留，请重新提交原步骤继续执行。",
            "details": {"workflow": workflow_id},
        }
        connection.execute(
            "UPDATE workflow_jobs SET status='failed', progress_message=?, error_json=?, "
            "finished_at=?, updated_at=? WHERE workflow=? AND status IN ('queued', 'running')",
            ("任务因 MCP 服务退出而中断", json.dumps(error, ensure_ascii=False), now, now, workflow_id),
        )
        connection.commit()
    finally:
        connection.close()


def enqueue_job(
    workflow: str,
    job_type: str,
    payload: dict,
    *,
    handler: str,
    database_path: str | Path | None = None,
) -> dict:
    """提交后台任务；同一工作流下相同输入仍在排队或运行时直接返回原任务。"""
    workflow_id = _workflow_id(workflow)
    if not str(job_type or "").strip():
        raise InvalidParameterError("job_type", "job_type 不能为空")
    if not isinstance(payload, dict):
        raise InvalidParameterError("payload", "payload 必须是对象")
    handler_value = _handler(handler)
    database = Path(database_path or DEFAULT_DATABASE_PATH).resolve()
    request_key = _request_key(workflow_id, str(job_type).strip(), payload)
    connection = _connect(database)
    try:
        existing = connection.execute(
            "SELECT * FROM workflow_jobs WHERE workflow=? AND job_type=? AND request_key=? "
            "AND status IN ('queued', 'running') ORDER BY created_at DESC LIMIT 1",
            (workflow_id, str(job_type).strip(), request_key),
        ).fetchone()
        if existing:
            return _decode(existing)
        job_id = f"job-{uuid4().hex}"
        now = _timestamp()
        connection.execute(
            "INSERT INTO workflow_jobs(job_id, workflow, job_type, handler, request_key, status, "
            "progress_message, input_json, created_at, updated_at, schema_version) "
            "VALUES (?, ?, ?, ?, ?, 'queued', ?, ?, ?, ?, ?)",
            (
                job_id,
                workflow_id,
                str(job_type).strip(),
                handler_value,
                request_key,
                "任务已进入后台队列",
                json.dumps(payload, ensure_ascii=False),
                now,
                now,
                JOB_SCHEMA_VERSION,
            ),
        )
        connection.commit()
    finally:
        connection.close()
    _ensure_worker()
    _QUEUE.put((job_id, database))
    return get_job(job_id, database_path=database)


def get_job(
    job_id: str,
    database_path: str | Path | None = None,
    *,
    workflow: str | None = None,
) -> dict:
    """查询后台任务状态和结果。"""
    if not isinstance(job_id, str) or not re.fullmatch(JOB_ID_PATTERN, job_id.strip()):
        raise InvalidParameterError("job_id", f"job_id 必须是 job- 加 32 位十六进制，当前为 {job_id!r}")
    database = Path(database_path or DEFAULT_DATABASE_PATH).resolve()
    connection = _connect(database)
    try:
        row = connection.execute(
            "SELECT * FROM workflow_jobs WHERE job_id=?",
            (job_id.strip(),),
        ).fetchone()
    finally:
        connection.close()
    if row is None:
        raise JobNotFoundError(
            f"没有找到后台任务：{job_id}",
            {"job_id": job_id, "database_path": str(database)},
        )
    decoded = _decode(row)
    if workflow is not None and decoded["workflow"] != _workflow_id(workflow):
        raise JobNotFoundError(
            f"后台任务不属于工作流 {workflow}：{job_id}",
            {"job_id": job_id, "workflow": workflow, "actual_workflow": decoded["workflow"]},
        )
    return decoded
