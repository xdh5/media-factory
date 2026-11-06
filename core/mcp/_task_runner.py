"""MCP 共享后台任务：文件状态 + 线程池，供耗时步骤 start/poll。"""

from __future__ import annotations

import inspect
import json
import os
import sys
import tempfile
import threading
import traceback
import uuid
from concurrent.futures import ThreadPoolExecutor
from datetime import datetime, timezone
from hashlib import sha256
from pathlib import Path
from typing import Callable

from filelock import FileLock, Timeout

TASKS_DIR_NAME = "tasks"
STATUS_RUNNING = "running"
STATUS_SUCCEEDED = "succeeded"
STATUS_FAILED = "failed"

_executor = ThreadPoolExecutor(max_workers=4, thread_name_prefix="mcp-task")
_registry_lock = threading.Lock()
_run_locks: dict[str, threading.Lock] = {}


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


def _read_task(path: Path) -> dict:
    data = json.loads(path.read_text(encoding="utf-8"))
    if data["status"] != STATUS_RUNNING:
        return data
    try:
        with FileLock(path.with_suffix(".lock"), timeout=0):
            data = json.loads(path.read_text(encoding="utf-8"))
            if data["status"] == STATUS_RUNNING:
                data["status"] = STATUS_FAILED
                data["progress"] = None
                data["error"] = {
                    "message": "MCP 进程已退出，后台任务已中断。请重新启动该步骤。",
                    "type": "OrphanTaskError",
                }
                _write_task(path, data)
    except Timeout:
        pass
    return data


def _find_running_task(base: Path, run_id: str, step: str) -> dict | None:
    for path in base.glob("task-*.json"):
        try:
            data = json.loads(path.read_text(encoding="utf-8"))
        except (OSError, json.JSONDecodeError):
            continue
        if data.get("run_id") == run_id and data.get("step") == step and data.get("status") == STATUS_RUNNING:
            data = _read_task(path)
            if data["status"] == STATUS_RUNNING:
                return data
    return None


def _write_task(path: Path, data: dict) -> None:
    data["updated_at"] = _utc_now()
    try:
        text = json.dumps(data, ensure_ascii=False, indent=2)
    except TypeError as exc:
        print(f"[后台任务] JSON 序列化失败，改用 str 兜底：{exc}", file=sys.stderr, flush=True)
        text = json.dumps(data, ensure_ascii=False, indent=2, default=str)
    # 在同一目录写完临时文件再原子替换，避免轮询读到空文件或半份 JSON。
    temporary_path = None
    try:
        with tempfile.NamedTemporaryFile(
            mode="w", encoding="utf-8", dir=path.parent,
            prefix=f".{path.name}.", suffix=".tmp", delete=False,
        ) as temporary:
            temporary_path = Path(temporary.name)
            temporary.write(text)
        os.replace(temporary_path, path)
    finally:
        if temporary_path is not None:
            temporary_path.unlink(missing_ok=True)


def submit_task(
    *,
    cache_dir: Path,
    run_id: str,
    step: str,
    fn: Callable[..., dict],
) -> dict:
    """提交后台任务并立即返回 task_id。"""
    base = tasks_dir(cache_dir)
    with FileLock(base / "submit.lock"):
        return _submit_task(base, run_id, step, fn)


def _submit_task(base: Path, run_id: str, step: str, fn: Callable[..., dict]) -> dict:
    existing = _find_running_task(base, run_id, step)
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
    path = base / f"{task_id}.json"
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
    ownership = FileLock(path.with_suffix(".lock"), thread_local=False)
    ownership.acquire()
    run_key = sha256(run_id.encode()).hexdigest()

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
        run_file_lock = FileLock(base / f"run-{run_key}.lock")
        lock = _run_lock(run_id)
        lock.acquire()
        try:
            run_file_lock.acquire()
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
            trace = traceback.format_exc()
            print(
                f"[后台任务失败] {task_id} step={step} {type(extra).__name__}: {extra}\n{trace}",
                file=sys.stderr, flush=True,
            )
            data = json.loads(path.read_text(encoding="utf-8"))
            data["status"] = STATUS_FAILED
            data["error"] = {
                "message": str(extra),
                "type": type(extra).__name__,
                "traceback": trace,
            }
            if isinstance(getattr(extra, "details", None), dict):
                data["error"]["details"] = extra.details
            _write_task(path, data)
        finally:
            run_file_lock.release()
            lock.release()
            ownership.release()

    try:
        _write_task(path, payload)
        _executor.submit(_worker)
    except BaseException:
        ownership.release()
        raise
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

    data = _read_task(path)

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
