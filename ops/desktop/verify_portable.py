"""实际启动绿色版，验证 Open WebUI 窗口、运行时独立性与退出清理。"""

import ctypes
from ctypes import wintypes
import json
import os
from pathlib import Path
import socket
import subprocess
import time
import uuid
import sys

ROOT = Path(__file__).resolve().parents[2]
executable = ROOT / "dist/MediaFactory/MediaFactory.exe"
if not executable.is_file() or not (executable.parent / "构建信息.json").is_file():
    raise RuntimeError("没有通过完整构建的绿色版")
home = ROOT / "cache/desktop-verification" / ("portable-" + uuid.uuid4().hex)
environment = {name: value for name, value in os.environ.items() if not name.startswith(("AGENT_", "DASHSCOPE_", "R2_", "CLOUDFLARE_")) and name not in {"ELECTRON_RUN_AS_NODE", "NODE_OPTIONS", "DY_COOKIES", "PYTHONPATH", "PYTHONHOME"}}
environment["MEDIA_FACTORY_HOME"] = str(home)
if "--with-model" in sys.argv:
    from dotenv import dotenv_values
    configuration = dotenv_values(ROOT / ".env")
    selected = {name: configuration[name] for name in ("DASHSCOPE_API_KEY_FINANCE", "DASHSCOPE_BASE_URL") if configuration.get(name)}
    selected.update({"DASHSCOPE_BUSINESS_LINE": "finance", "DASHSCOPE_MODEL": "qwen3.7-plus"})
    home.mkdir(parents=True)
    (home / "config.env").write_text("\n".join(name + "=" + json.dumps(value) for name, value in selected.items()), encoding="utf-8")
    environment["MEDIA_FACTORY_VERIFY_REAL_MODEL"] = "1"
# 子进程仅使用内嵌运行时，不借助开发机 Python、Node 或 FFmpeg 搜索路径。
environment["PATH"] = os.path.join(os.environ["SystemRoot"], "System32")
process = subprocess.Popen([str(executable), "--verify-desktop", "--disable-gpu"], env=environment,
                           stdout=subprocess.DEVNULL, stderr=subprocess.DEVNULL)
try:
    process.wait(timeout=660)
finally:
    if process.poll() is None:
        process.terminate()
        process.wait(timeout=15)
record = home / "desktop-verification.json"
if not record.is_file():
    raise RuntimeError("绿色版没有完成窗口验收，请查看 " + str(home / "logs"))
report = json.loads(record.read_text(encoding="utf-8"))
if report.get("homeTitle") != "Media Factory" or not report.get("modelName"):
    raise RuntimeError("首页应用标题或实际模型名称不符合预期")
if report["modelCount"] != 1 or report.get("webuiModelCount") != 1 or report.get("chatWindowCount") != 1 or "127.0.0.1" not in report["url"] or len(report["visibleText"]) < 30 or not (home / "desktop-window.png").is_file():
    raise RuntimeError("Open WebUI 窗口或模型发现不符合预期")
if "--with-model" in sys.argv and (report.get("relayStatus") != 200 or not report.get("relayReply")):
    raise RuntimeError("原版 Open WebUI 到 Agent 的真实模型转发没有完成")
time.sleep(2)
for port in (report["agentPort"], report["webuiPort"]):
    with socket.socket() as connection:
        connection.settimeout(1)
        if connection.connect_ex(("127.0.0.1", port)) == 0:
            raise RuntimeError("客户端退出后仍有后台端口监听")
kernel = ctypes.WinDLL("kernel32", use_last_error=True)
kernel.OpenProcess.restype = wintypes.HANDLE
kernel.GetExitCodeProcess.argtypes = [wintypes.HANDLE, ctypes.POINTER(wintypes.DWORD)]
kernel.CloseHandle.argtypes = [wintypes.HANDLE]
handle = kernel.OpenProcess(0x1000, False, report["backendPid"])
if handle:
    code = wintypes.DWORD()
    kernel.GetExitCodeProcess(handle, ctypes.byref(code))
    kernel.CloseHandle(handle)
    if code.value == 259:
        raise RuntimeError("监督进程未退出")
report["checks"] = ["真实 Open WebUI 窗口已渲染", "无开发机 Python/Node/FFmpeg PATH 依赖", "真实千问模型可发现", "退出后本地服务端口关闭", "监督进程已退出"]
report["status"] = "passed"
record.write_text(json.dumps(report, ensure_ascii=False, indent=2), encoding="utf-8")
print("PORTABLE_DESKTOP_PASSED")
print(record)
print(home / "desktop-window.png")
