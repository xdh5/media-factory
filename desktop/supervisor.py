"""启动本地服务，隔离数据目录并回收自身进程树。"""

import argparse
import ctypes
from ctypes import wintypes
import json
import os
from pathlib import Path
import shutil
import socket
import secrets
import subprocess
import sys
import threading
import time
import urllib.request


def windows_job():
    """关闭作业句柄时终止本进程及其后代，不影响其他 Python 进程。"""
    if sys.platform != "win32":
        return None
    kernel = ctypes.WinDLL("kernel32", use_last_error=True)
    kernel.CreateJobObjectW.restype = wintypes.HANDLE
    kernel.SetInformationJobObject.argtypes = [wintypes.HANDLE, ctypes.c_int, ctypes.c_void_p, wintypes.DWORD]
    kernel.AssignProcessToJobObject.argtypes = [wintypes.HANDLE, wintypes.HANDLE]
    kernel.GetCurrentProcess.restype = wintypes.HANDLE
    class BasicLimit(ctypes.Structure):
        _fields_ = [("PerProcessUserTimeLimit", ctypes.c_int64), ("PerJobUserTimeLimit", ctypes.c_int64),
                    ("LimitFlags", wintypes.DWORD), ("MinimumWorkingSetSize", ctypes.c_size_t),
                    ("MaximumWorkingSetSize", ctypes.c_size_t), ("ActiveProcessLimit", wintypes.DWORD),
                    ("Affinity", ctypes.c_size_t), ("PriorityClass", wintypes.DWORD), ("SchedulingClass", wintypes.DWORD)]
    class IO(ctypes.Structure):
        _fields_ = [(name, ctypes.c_uint64) for name in ("ReadOperationCount", "WriteOperationCount", "OtherOperationCount", "ReadTransferCount", "WriteTransferCount", "OtherTransferCount")]
    class ExtendedLimit(ctypes.Structure):
        _fields_ = [("BasicLimitInformation", BasicLimit), ("IoInfo", IO), ("ProcessMemoryLimit", ctypes.c_size_t),
                    ("JobMemoryLimit", ctypes.c_size_t), ("PeakProcessMemoryUsed", ctypes.c_size_t), ("PeakJobMemoryUsed", ctypes.c_size_t)]
    handle = kernel.CreateJobObjectW(None, None)
    information = ExtendedLimit()
    information.BasicLimitInformation.LimitFlags = 0x2000
    if not handle or not kernel.SetInformationJobObject(handle, 9, ctypes.byref(information), ctypes.sizeof(information)):
        raise ctypes.WinError(ctypes.get_last_error())
    if not kernel.AssignProcessToJobObject(handle, kernel.GetCurrentProcess()):
        raise ctypes.WinError(ctypes.get_last_error())
    return handle


def free_port():
    with socket.socket() as listener:
        listener.bind(("127.0.0.1", 0))
        return listener.getsockname()[1]


def main():
    parser = argparse.ArgumentParser()
    parser.add_argument("--home", type=Path, required=True)
    parser.add_argument("--bundle", type=Path, required=True)
    parser.add_argument("--parent-pid", type=int, required=True)
    parser.add_argument("--ready-file", type=Path, required=True)
    args = parser.parse_args()
    job = windows_job()
    home = args.home.resolve()
    workspace = home / "workspace"
    # 代码随版本刷新，data/cache 和配置始终保留在外部工作目录。
    def copy_changed(source, target):
        if not Path(target).is_file() or Path(source).stat().st_size != Path(target).stat().st_size or Path(source).stat().st_mtime != Path(target).stat().st_mtime:
            shutil.copy2(source, target)
        return target
    shutil.copytree(args.bundle / "project", workspace, dirs_exist_ok=True, copy_function=copy_changed,
                    ignore=shutil.ignore_patterns("data", "cache", ".env", "__pycache__", "node_modules"))
    publisher_modules = workspace / "integrations/media-publisher/node_modules"
    packaged_modules = (args.bundle / "project/integrations/media-publisher/node_modules").resolve()
    if os.path.isjunction(publisher_modules) and publisher_modules.resolve() != packaged_modules:
        publisher_modules.rmdir()
    if not publisher_modules.exists():
        powershell = Path(os.environ["SystemRoot"]) / "System32/WindowsPowerShell/v1.0/powershell.exe"
        subprocess.run([str(powershell), "-NoProfile", "-NonInteractive", "-Command",
            "New-Item -ItemType Junction -Path $env:MF_DEPENDENCY_LINK -Target $env:MF_DEPENDENCY_TARGET | Out-Null"],
            env={**os.environ, "MF_DEPENDENCY_LINK": str(publisher_modules), "MF_DEPENDENCY_TARGET": str(packaged_modules)},
            creationflags=0x08000000, check=True)
    home.mkdir(parents=True, exist_ok=True)
    (home / "logs").mkdir(exist_ok=True)
    (home / "open-webui").mkdir(exist_ok=True)
    sys.path.insert(0, str(workspace))
    import desktop
    desktop.__path__ = [str(workspace / "desktop")]
    from dotenv import dotenv_values
    # 项目内运行直接复用原配置；绿色版搬离项目后仍使用外部持久化配置。
    project_root = next((parent for parent in args.bundle.resolve().parents
                         if (parent / "pyproject.toml").is_file() and (parent / "core").is_dir()), None)
    source_configuration = project_root / ".env" if project_root else home / "workspace/.env"
    if project_root:
        # 各集成仍从自己的目录读取配置，密钥只同步到外部工作区，不进入绿色版资源。
        for integration in (project_root / "integrations").iterdir():
            source = integration / ".env"
            if source.is_file():
                target = workspace / "integrations" / integration.name / ".env"
                target.parent.mkdir(parents=True, exist_ok=True)
                shutil.copy2(source, target)
    configuration = {key: value for key, value in dotenv_values(source_configuration).items() if value is not None}
    configuration.update({key: value for key, value in dotenv_values(home / "config.env").items() if value is not None})
    if project_root and source_configuration.is_file() and not (home / "config.env").exists():
        shutil.copy2(source_configuration, home / "config.env")
    if not configuration.get("AGENT_API_KEY") and configuration.get("DASHSCOPE_API_KEY_FINANCE"):
        configuration.update({"AGENT_API_KEY": configuration["DASHSCOPE_API_KEY_FINANCE"],
                              "AGENT_BASE_URL": configuration.get("DASHSCOPE_BASE_URL") or "https://dashscope.aliyuncs.com/compatible-mode/v1",
                              "AGENT_MODEL": configuration.get("AGENT_MODEL") or "deepseek-v4-pro"})
    os.environ.update(configuration)
    from agent.diagnostics.redaction import redact
    (home / "shutdown.request").unlink(missing_ok=True)
    os.environ.update({"MEDIA_FACTORY_HOME": str(home), "MEDIA_FACTORY_WORKSPACE": str(workspace),
                       "MEDIA_FACTORY_AGENT_DATABASE": str(home / "agent.sqlite"), "PYTHONPATH": str(workspace),
                       "PYTHONUTF8": "1", "DASHSCOPE_BUSINESS_LINE": configuration.get("DASHSCOPE_BUSINESS_LINE", "finance")})
    ports = {"agent": free_port(), "webui": free_port()}
    os.environ["MEDIA_FACTORY_AGENT_PORT"] = str(ports["agent"])
    os.environ["MEDIA_FACTORY_WEBUI_PORT"] = str(ports["webui"])
    token = os.environ["MEDIA_FACTORY_SESSION_TOKEN"]
    webui_secret_file = home / "webui-secret.key"
    if not webui_secret_file.exists():
        webui_secret_file.write_text(secrets.token_hex(32), encoding="utf-8")
    os.environ["WEBUI_SECRET_KEY"] = webui_secret_file.read_text(encoding="utf-8")
    common = dict(os.environ)
    webui = {**common, "DATA_DIR": str(home / "open-webui"), "STATIC_DIR": str(home / "open-webui/static"), "WEBUI_AUTH": "false", "ENABLE_PERSISTENT_CONFIG": "false",
             "CORS_ALLOW_ORIGIN": f"http://127.0.0.1:{ports['webui']}",
             "OPENAI_API_BASE_URL": f"http://127.0.0.1:{ports['agent']}/v1", "OPENAI_API_KEY": token,
             "OPENAI_API_BASE_URLS": f"http://127.0.0.1:{ports['agent']}/v1", "OPENAI_API_KEYS": token,
             "ENABLE_FORWARD_USER_INFO_HEADERS": "true", "ENABLE_OLLAMA_API": "false", "OFFLINE_MODE": "true",
             "HF_HUB_OFFLINE": "1", "RAG_EMBEDDING_ENGINE": "openai", "ENABLE_TITLE_GENERATION": "false",
             "ENABLE_TAGS_GENERATION": "false", "ENABLE_FOLLOW_UP_GENERATION": "false", "ANONYMIZED_TELEMETRY": "false",
             "ENABLE_AUTOCOMPLETE_GENERATION": "false", "ENABLE_SEARCH_QUERY_GENERATION": "false",
             "ENABLE_RETRIEVAL_QUERY_GENERATION": "false", "ENABLE_IMAGE_PROMPT_GENERATION": "false",
             "DO_NOT_TRACK": "true", "SCARF_NO_ANALYTICS": "true", "WEBUI_SECRET_KEY": webui_secret_file.read_text(encoding="utf-8")}
    webui.update({"RAG_EMBEDDING_MODEL_AUTO_UPDATE": "false", "RAG_RERANKING_MODEL_AUTO_UPDATE": "false",
                  "WHISPER_MODEL_AUTO_UPDATE": "false", "ENABLE_VERSION_UPDATE_CHECK": "false"})
    children = []
    def log_output(process, name):
        with (home / "logs" / (name + ".log")).open("a", encoding="utf-8") as stream:
            for line in process.stdout:
                stream.write(redact(line))
                stream.flush()
    try:
        for name, module, environment, port in (("agent", "desktop.gateway:app", common, ports["agent"]),
                                                  ("open-webui", "open_webui.main:app", webui, ports["webui"])):
            command = ([sys.executable, "-m", "uvicorn", module, "--host", "127.0.0.1", "--port", str(port), "--no-access-log"]
                       if name == "agent" else [sys.executable, "-c", f"from open_webui import serve; serve(host='127.0.0.1', port={port})"])
            process = subprocess.Popen(command,
                cwd=workspace, env=environment, stdout=subprocess.PIPE, stderr=subprocess.STDOUT,
                text=True, encoding="utf-8", errors="replace", creationflags=0x08000000 if sys.platform == "win32" else 0)
            children.append(process)
            threading.Thread(target=log_output, args=(process, name), daemon=True).start()
        for _ in range(360):
            if any(process.poll() is not None for process in children):
                raise RuntimeError("本地服务提前退出，请查看脱敏日志")
            try:
                for port, route in ((ports["agent"], "/health"), (ports["webui"], "/health")):
                    urllib.request.urlopen(f"http://127.0.0.1:{port}{route}", timeout=1).close()
                break
            except OSError:
                time.sleep(0.5)
        else:
            raise TimeoutError("本地服务启动超时")
        args.ready_file.write_text(json.dumps(ports), encoding="utf-8")
        while not (home / "shutdown.request").exists():
            if any(process.poll() is not None for process in children):
                raise RuntimeError("本地服务退出")
            if sys.platform == "win32":
                kernel = ctypes.WinDLL("kernel32", use_last_error=True)
                kernel.OpenProcess.restype = wintypes.HANDLE
                handle = kernel.OpenProcess(0x1000, False, args.parent_pid)
                if not handle:
                    break
                code = wintypes.DWORD()
                kernel.GetExitCodeProcess.argtypes = [wintypes.HANDLE, ctypes.POINTER(wintypes.DWORD)]
                kernel.GetExitCodeProcess(handle, ctypes.byref(code))
                kernel.CloseHandle.argtypes = [wintypes.HANDLE]
                kernel.CloseHandle(handle)
                if code.value != 259:
                    break
            time.sleep(0.5)
    finally:
        (home / "shutdown.request").unlink(missing_ok=True)
        args.ready_file.unlink(missing_ok=True)
        for process in children:
            if process.poll() is None:
                process.terminate()
        # 作业对象句柄随进程退出释放，回收残留的 MCP 和 ffmpeg 后代。


if __name__ == "__main__":
    try:
        main()
    except Exception:
        import traceback
        from agent.diagnostics.redaction import redact
        log_root = Path(sys.argv[sys.argv.index("--home") + 1]) / "logs"
        log_root.mkdir(parents=True, exist_ok=True)
        (log_root / "supervisor.log").write_text(redact(traceback.format_exc()), encoding="utf-8")
        raise
