"""实际启动 Windows 进程树，验证作业对象释放后的后代回收。"""

import json
import os
from pathlib import Path
import subprocess
import sys
import time
import uuid

ROOT = Path(__file__).resolve().parents[2]
directory = ROOT / "cache/desktop-verification" / ("process-" + uuid.uuid4().hex)
directory.mkdir(parents=True)
script = directory / "parent.py"
script.write_text('''import sys, subprocess, time, json
from pathlib import Path
sys.path.insert(0, sys.argv[2])
from core.desktop.supervisor import windows_job
job = windows_job()
child = subprocess.Popen([sys.executable, "-c", "import time; time.sleep(120)"])
Path(sys.argv[1]).write_text(json.dumps({"parent": __import__("os").getpid(), "child": child.pid}))
time.sleep(1)
''', encoding="utf-8")
record = directory / "pids.json"
process = subprocess.Popen([sys.executable, str(script), str(record), str(ROOT)], cwd=ROOT)
process.wait(timeout=15)
identities = json.loads(record.read_text())
time.sleep(1)
import ctypes
from ctypes import wintypes
kernel = ctypes.WinDLL("kernel32", use_last_error=True)
kernel.OpenProcess.restype = wintypes.HANDLE
kernel.GetExitCodeProcess.argtypes = [wintypes.HANDLE, ctypes.POINTER(wintypes.DWORD)]
kernel.CloseHandle.argtypes = [wintypes.HANDLE]
handle = kernel.OpenProcess(0x1000, False, identities["child"])
if handle:
    code = wintypes.DWORD()
    kernel.GetExitCodeProcess(handle, ctypes.byref(code))
    kernel.CloseHandle(handle)
    if code.value == 259:
        raise RuntimeError("Windows 后代进程未回收")
print("WINDOWS_PROCESS_TREE_CLEANUP_PASSED", identities)
