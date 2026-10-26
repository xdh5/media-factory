"""独立发布批次：进程和完整记录留在本地，不依赖模型轮询。"""

from contextlib import contextmanager
from datetime import datetime, timezone
import json
import os
from pathlib import Path
import subprocess
import sys
import uuid

from ..config.settings import CACHE_ROOT, PROJECT_ROOT

BATCH_ROOT = CACHE_ROOT / "batches"
ACTIVE_STATUSES = {"queued", "running"}


def process_is_running(pid: int) -> bool:
    if os.name == "nt":
        import ctypes
        from ctypes import wintypes
        kernel = ctypes.WinDLL("kernel32", use_last_error=True)
        kernel.OpenProcess.restype = wintypes.HANDLE
        handle = kernel.OpenProcess(0x1000, False, pid)
        if not handle:
            if ctypes.get_last_error() == 87:
                return False
            raise ctypes.WinError(ctypes.get_last_error())
        code = wintypes.DWORD()
        try:
            if not kernel.GetExitCodeProcess(wintypes.HANDLE(handle), ctypes.byref(code)):
                raise ctypes.WinError(ctypes.get_last_error())
            return code.value == 259
        finally:
            kernel.CloseHandle(wintypes.HANDLE(handle))
    try:
        os.kill(pid, 0)
        return True
    except ProcessLookupError:
        return False


def write_batch(path: Path, data: dict) -> None:
    data["updated_at"] = datetime.now(timezone.utc).isoformat()
    temporary = path.with_suffix(".tmp")
    temporary.write_text(json.dumps(data, ensure_ascii=False, indent=2), encoding="utf-8")
    temporary.replace(path)


@contextmanager
def account_batch_lock(account_group: str, wait: bool = False):
    """同一账号组的批次互斥，避免不同 MCP 进程重复提交。"""
    BATCH_ROOT.mkdir(parents=True, exist_ok=True)
    with (BATCH_ROOT / f"{account_group}.lock").open("a+b") as handle:
        handle.write(b"0")
        handle.flush()
        handle.seek(0)
        if os.name == "nt":
            import msvcrt
            msvcrt.locking(handle.fileno(), msvcrt.LK_LOCK if wait else msvcrt.LK_NBLCK, 1)
        else:
            import fcntl
            fcntl.flock(handle, fcntl.LOCK_EX | (0 if wait else fcntl.LOCK_NB))
        try:
            yield
        finally:
            handle.seek(0)
            if os.name == "nt":
                msvcrt.locking(handle.fileno(), msvcrt.LK_UNLCK, 1)
            else:
                fcntl.flock(handle, fcntl.LOCK_UN)


def read_batch(job_path: str) -> dict:
    path = Path(job_path).resolve()
    if not path.is_relative_to(BATCH_ROOT.resolve()) or path.suffix != ".json":
        raise ValueError("批次路径必须位于发布批次缓存目录")
    data = json.loads(path.read_text(encoding="utf-8"))
    pid_path = path.with_suffix(".pid")
    if data["status"] in ACTIVE_STATUSES and pid_path.is_file():
        if not process_is_running(int(pid_path.read_text())):
            data.update(status="interrupted", error={"message": "后台进程已退出，请核对已入库回执后恢复批次"})
            write_batch(path, data)
    elif data["status"] == "queued" and (datetime.now(timezone.utc) - datetime.fromisoformat(data["updated_at"])).total_seconds() > 30:
        data.update(status="interrupted", error={"message": "启动器未创建工作进程，尚未执行发布"})
        write_batch(path, data)
    return data


def batch_summary(data: dict) -> dict:
    interaction = Path(data["job_path"]).with_suffix(".interaction.json")
    summary = {key: data.get(key) for key in (
        "job_id", "job_path", "status", "current_date", "completed_dates", "scheduled_count",
        "duplicate_count", "progress", "error", "prepare_only", "updated_at",
    )}
    if data["status"] in ACTIVE_STATUSES and interaction.is_file():
        summary["interaction"] = json.loads(interaction.read_text(encoding="utf-8"))
        summary["progress"] = summary["interaction"]["message"]
    return summary


def start_worker(path: Path, env: dict) -> int:
    command = [sys.executable, "-m", "core.mcp.publishing.workflows.batch_runner", str(path)]
    if os.name == "nt":
        # 由本机进程管理服务创建独立工作进程，MCP 的作业对象退出时不会连带终止它。
        script = (
            "$ErrorActionPreference='Stop'; "
            "$startup = New-CimInstance -ClassName Win32_ProcessStartup -ClientOnly -Property @{ShowWindow=[UInt16]0}; "
            "$created = Invoke-CimMethod -ClassName Win32_Process -MethodName Create -Arguments "
            "@{CommandLine=$env:MEDIA_FACTORY_BATCH_COMMAND;CurrentDirectory=$env:MEDIA_FACTORY_BATCH_DIRECTORY;"
            "ProcessStartupInformation=$startup}; $created | ConvertTo-Json -Compress"
        )
        result = subprocess.run(
            ["powershell.exe", "-NoProfile", "-NonInteractive", "-Command", script],
            env={**env, "MEDIA_FACTORY_BATCH_COMMAND": subprocess.list2cmdline(command),
                 "MEDIA_FACTORY_BATCH_DIRECTORY": str(PROJECT_ROOT)},
            capture_output=True, creationflags=subprocess.CREATE_NO_WINDOW, timeout=30,
        )
        if result.returncode or not result.stdout.strip():
            raise OSError(f"启动后台批次失败：{result.stderr.decode('mbcs', errors='replace').strip()[:300]}")
        created = json.loads(result.stdout)
        if created["ReturnValue"] != 0:
            raise OSError(f"本机进程服务启动批次失败：{created['ReturnValue']}")
        return int(created["ProcessId"])
    with path.with_suffix(".log").open("ab") as output:
        return subprocess.Popen(command, cwd=PROJECT_ROOT, env=env, stdin=subprocess.DEVNULL,
                                stdout=output, stderr=output, start_new_session=True).pid


def launch_batch(request: dict) -> dict:
    BATCH_ROOT.mkdir(parents=True, exist_ok=True)
    group = request["account_group"]
    for path in BATCH_ROOT.glob("batch-*.json"):
        data = read_batch(str(path))
        if data["request"]["account_group"] == group and data["status"] in ACTIVE_STATUSES:
            if data["request"] != request:
                raise ValueError("该账号组已有其他后台批次，请先查询现有批次")
            return {**batch_summary(data), "reused": True}
    with account_batch_lock(group):
        job_id = f"batch-{uuid.uuid4().hex[:12]}"
        path = BATCH_ROOT / f"{job_id}.json"
        data = {"job_id": job_id, "job_path": str(path), "status": "queued", "request": request,
                "prepare_only": request["prepare_only"], "completed_dates": [],
                "scheduled_count": 0, "duplicate_count": 0, "error": None}
        write_batch(path, data)
        env = dict(os.environ)
        env.pop("MEDIA_PUBLISHER_PARENT_PID", None)
        env.pop("MEDIA_PUBLISHER_OWNER_PID", None)
        try:
            pid = start_worker(path, env)
            path.with_suffix(".pid").write_text(str(pid), encoding="utf-8")
        except (OSError, subprocess.SubprocessError, ValueError) as error:
            data.update(status="failed", error={"message": str(error)})
            write_batch(path, data)
            raise
    return {**batch_summary(data), "reused": False,
            "notice": "后台程序独立执行。返回聊天后无需保持模型在线，不要循环查询普通进度；需要查看结果时查询一次。"}
