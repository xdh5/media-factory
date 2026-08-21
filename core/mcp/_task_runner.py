"""MCP 共享后台任务：文件状态 + 线程池，供耗时步骤 start/poll。"""

from __future__ import annotations

import inspect
import json
import threading
import traceback
import uuid
from concurrent.futures import ThreadPoolExecutor
from datetime import datetime, timezone
from pathlib import Path
from typing import Callable

TASKS_DIR_NAME = "tasks"
STATUS_RUNNING = "running"
STATUS_SUCCEEDED = "succeeded"
STATUS_FAILED = "failed"

_executor = ThreadPoolExecutor(max_workers=4, thread_name_prefix="mcp-task")
_registry_lock = threading.Lock()
_run_locks: dict[str, threading.Lock] = {}
_live_tasks: set[str] = set()


class TaskNotFoundError(Exception):
    """轮询时找不到任务文件。"""

    def __init__(self, task_ref: str):
        super().__init__(f"找不到任务：{task_ref}")
        self.task_ref = task_ref


class TaskAlreadyRunningError(Exception):
    """同一步骤已有进行中的任务。"""

    def __init__(self, task_id: str, step: str):
        super().__init__(
            f"步骤 {step} 已有进行中的任务：{task_id}；请用 poll_task 轮询，勿重复 start"
        )
        self.task_id = task_id
        self.step = step


def _utc_now() -> str:
    return datetime.now(timezone.utc).replace(microsecond=0).isoformat().replace("+00:00", "Z")


def tasks_dir(cache_dir: Path) -> Path:
    path = Path(cache_dir).resolve() / TASKS_DIR_NAME
    path.mkdir(parents=True, exist_ok=True)
    return path


def _run_lock(run_id: str) -> threading.Lock:
    with _registry_lock:
        if run_id not in _run_locks:
            _run_locks[run_id] = threading.Lock()
        return _run_locks[run_id]


def _task_path(cache_dir: Path, task_id: str) -> Path:
    return tasks_dir(cache_dir) / f"{task_id}.json"


def _fail_orphan_tasks(cache_dir: Path, run_id: str, step: str) -> None:
    """磁盘上仍写 running、但本进程没有 worker 的任务视为 MCP 重启后的孤儿。"""
    base = tasks_dir(cache_dir)
    with _registry_lock:
        live = set(_live_tasks)
    for path in base.glob("task-*.json"):
        try:
            data = json.loads(path.read_text(encoding="utf-8"))
        except (OSError, json.JSONDecodeError):
            continue
        if (
            data.get("run_id") != run_id
            or data.get("step") != step
            or data.get("status") != STATUS_RUNNING
        ):
            continue
        task_id = str(data.get("task_id") or "")
        if task_id in live:
            continue
        data["status"] = STATUS_FAILED
        data["error"] = {
            "message": "MCP 已重启，后台任务中断。请重新 start 该步骤，不要继续 poll 此任务。",
            "type": "OrphanTaskError",
        }
        _write_task(path, data)


def _find_running_task(cache_dir: Path, run_id: str, step: str) -> dict | None:
    base = tasks_dir(cache_dir)
    with _registry_lock:
        live = set(_live_tasks)
    for path in sorted(base.glob("task-*.json"), key=lambda item: item.stat().st_mtime, reverse=True):
        try:
            data = json.loads(path.read_text(encoding="utf-8"))
        except (OSError, json.JSONDecodeError):
            continue
        task_id = str(data.get("task_id") or "")
        if (
            data.get("run_id") == run_id
            and data.get("step") == step
            and data.get("status") == STATUS_RUNNING
            and task_id in live
        ):
            return {**data, "task_path": str(path), "reused": True}
    return None


def _write_task(path: Path, data: dict) -> None:
    data["updated_at"] = _utc_now()
    path.write_text(json.dumps(data, ensure_ascii=False, indent=2), encoding="utf-8")


def submit_task(
    *,
    cache_dir: Path,
    run_id: str,
    step: str,
    fn: Callable[..., dict],
) -> dict:
    """提交后台任务并立即返回 task_id。"""
    cache_dir = Path(cache_dir).resolve()
    _fail_orphan_tasks(cache_dir, run_id, step)
    existing = _find_running_task(cache_dir, run_id, step)
    if existing:
        return {
            "task_id": existing["task_id"],
            "task_path": existing["task_path"],
            "status": existing["status"],
            "step": step,
            "run_id": run_id,
            "reused": True,
        }

    task_id = f"task-{uuid.uuid4().hex[:12]}"
    path = _task_path(cache_dir, task_id)
    created = _utc_now()
    payload = {
        "task_id": task_id,
        "run_id": run_id,
        "step": step,
        "status": STATUS_RUNNING,
        "created_at": created,
        "updated_at": created,
        "progress": None,
        "result": None,
        "error": None,
        "task_path": str(path),
    }
    _write_task(path, payload)
    with _registry_lock:
        _live_tasks.add(task_id)

    def _progress(message: str) -> None:
        try:
            data = json.loads(path.read_text(encoding="utf-8"))
        except (OSError, json.JSONDecodeError):
            return
        if data.get("status") != STATUS_RUNNING:
            return
        data["progress"] = message
        _write_task(path, data)

    def _worker() -> None:
        lock = _run_lock(run_id)
        lock.acquire()
        try:
            kwargs = {}
            try:
                signature = inspect.signature(fn)
            except (TypeError, ValueError):
                signature = None
            if signature is not None and "progress" in signature.parameters:
                kwargs["progress"] = _progress
            result = fn(**kwargs)
            data = json.loads(path.read_text(encoding="utf-8"))
            data["status"] = STATUS_SUCCEEDED
            data["result"] = result
            data["progress"] = None
            _write_task(path, data)
        except Exception as extra:
            data = json.loads(path.read_text(encoding="utf-8"))
            data["status"] = STATUS_FAILED
            data["error"] = {
                "message": str(extra),
                "type": type(extra).__name__,
                "traceback": traceback.format_exc(),
            }
            _write_task(path, data)
        finally:
            with _registry_lock:
                _live_tasks.discard(task_id)
            lock.release()

    _executor.submit(_worker)
    return {
        "task_id": task_id,
        "task_path": str(path),
        "status": STATUS_RUNNING,
        "step": step,
        "run_id": run_id,
        "reused": False,
    }


def poll_task(*, task_path: str) -> dict:
    """读取任务状态；succeeded 时 result 有值，failed 时 error 有值。"""
    path = Path(task_path).resolve()
    if not path.is_file():
        raise TaskNotFoundError(str(path))

    data = json.loads(path.read_text(encoding="utf-8"))
    created = datetime.fromisoformat(str(data["created_at"]).replace("Z", "+00:00"))
    if data.get("status") == STATUS_RUNNING:
        duration = max((datetime.now(timezone.utc) - created).total_seconds(), 0.0)
    else:
        updated = datetime.fromisoformat(str(data["updated_at"]).replace("Z", "+00:00"))
        duration = max((updated - created).total_seconds(), 0.0)

    return {
        **data,
        "duration_seconds": round(duration, 3),
        "done": data.get("status") in (STATUS_SUCCEEDED, STATUS_FAILED),
    }
