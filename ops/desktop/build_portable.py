"""构建免安装目录；构建机需要 Windows x64 Python 3.12，成品不需要。"""

import argparse
from datetime import datetime, timezone
import hashlib
import json
import os
from pathlib import Path
import shutil
import subprocess
import sys
import urllib.request
import zipfile

ROOT = Path(__file__).resolve().parents[2]
CACHE = ROOT / "cache/desktop-build"


def copy_changed(source, target):
    source_path, target_path = Path(source), Path(target)
    if not target_path.is_file() or source_path.stat().st_size != target_path.stat().st_size or source_path.stat().st_mtime != target_path.stat().st_mtime:
        shutil.copy2(source, target)
    return target


def download(url, name):
    target = CACHE / name
    if not target.exists():
        print("下载：" + name, flush=True)
        temporary = target.with_suffix(target.suffix + ".partial")
        subprocess.run(["curl.exe", "--fail", "--location", "--retry", "4", "--retry-all-errors",
                        "--continue-at", "-", "--output", str(temporary), url], check=True)
        temporary.replace(target)
    return target


def main():
    parser = argparse.ArgumentParser(description="构建 Windows 绿色版")
    parser.add_argument("--output", type=Path, default=ROOT / "dist/MediaFactory")
    parser.add_argument("--electron-version", default="42.11.16")
    parser.add_argument("--prepare-only", action="store_true", help="只准备运行时及项目资源，不视为完整构建")
    parser.add_argument("--reuse-runtime", action="store_true", help="复用已安装的界面与 Agent 依赖，仍执行导入检查")
    args = parser.parse_args()
    if sys.platform != "win32" or sys.version_info[:2] != (3, 12):
        raise RuntimeError("请使用 Windows x64 Python 3.12 构建")
    output = args.output.resolve()
    output.mkdir(parents=True, exist_ok=True)
    CACHE.mkdir(parents=True, exist_ok=True)
    version = args.electron_version
    name = f"electron-v{version}-win32-x64.zip"
    base = f"https://github.com/electron/electron/releases/download/v{version}"
    archive = download(f"{base}/{name}", name)
    sums = download(f"{base}/SHASUMS256.txt", f"electron-{version}-SHASUMS256.txt")
    expected = next(line.split()[0] for line in sums.read_text().splitlines() if line.split()[-1].lstrip("*") == name)
    if hashlib.sha256(archive.read_bytes()).hexdigest() != expected:
        raise RuntimeError("Electron 校验失败")
    executable = output / "MediaFactory.exe"
    reuse_electron = args.reuse_runtime and executable.is_file() and (output / "version").read_text().strip() == version
    if not reuse_electron:
        with zipfile.ZipFile(archive) as source:
            source.extractall(output)
    if executable.exists() and not reuse_electron:
        executable.replace(output / "MediaFactory.incomplete.exe")
    if (output / "electron_wer.dll").exists():
        (output / "electron_wer.dll").replace(output / "MediaFactory_wer.dll")
    application = output / "resources/app"
    application.mkdir(parents=True, exist_ok=True)
    for name in ("main.cjs", "package.json", "branding.js"):
        shutil.copy2(ROOT / "desktop" / name, application / name)
    project = application / "project"
    project.mkdir(exist_ok=True)
    ignored = shutil.ignore_patterns(".git", "node_modules", "__pycache__", ".env", "data", "cache", "*.sqlite*", "*.db", "*.log", "client_secret*.json", "*token.json")
    for name in ("core", "agent", "desktop", "integrations", "static", "docs"):
        shutil.copytree(ROOT / name, project / name, ignore=ignored, dirs_exist_ok=True, copy_function=copy_changed)
    (project / "ops").mkdir(exist_ok=True)
    shutil.copy2(ROOT / "ops/__init__.py", project / "ops/__init__.py")
    for name in ("anime", "github_actions"):
        shutil.copytree(ROOT / "ops" / name, project / "ops" / name, ignore=ignored,
                        dirs_exist_ok=True, copy_function=copy_changed)
    shutil.copytree(ROOT / "evals", project / "evals", ignore=ignored, dirs_exist_ok=True, copy_function=copy_changed)
    publisher = ROOT / "integrations/media-publisher"
    if not (publisher / "node_modules/electron/dist/electron.exe").is_file() or not (publisher / "dist/electron/main.js").is_file():
        raise RuntimeError("构建机需要先在 integrations/media-publisher 执行 npm ci 与 npm run build:dir")
    shutil.copytree(publisher / "node_modules", project / "integrations/media-publisher/node_modules",
                    ignore=shutil.ignore_patterns(".cache", "__pycache__"), dirs_exist_ok=True, copy_function=copy_changed)
    for name in ("agents.md", "pyproject.toml", "LICENSE", ".env.example"):
        shutil.copy2(ROOT / name, project / name)
    runtime = application / "python"
    runtime.mkdir(exist_ok=True)
    python_archive = download("https://www.python.org/ftp/python/3.12.10/python-3.12.10-embed-amd64.zip", "python-3.12.10-embed-amd64.zip")
    if not args.reuse_runtime or not (runtime / "python.exe").is_file():
        with zipfile.ZipFile(python_archive) as source:
            source.extractall(runtime)
    (runtime / "python312._pth").write_text("python312.zip\n.\nLib/site-packages\n../project\nimport site\n", encoding="utf-8")
    agent_packages = application / "agent-packages"
    agent_packages.mkdir(exist_ok=True)
    site = runtime / "Lib/site-packages"
    site.mkdir(parents=True, exist_ok=True)
    (site / "sitecustomize.py").write_text(
        '\"\"\"加载外部工作区与进程专用依赖。\"\"\"\n'
        'import os, sys\n'
        'root = os.getenv("MEDIA_FACTORY_WORKSPACE")\n'
        'if root:\n    sys.path.insert(0, root)\n'
        'packages = os.getenv("MEDIA_FACTORY_AGENT_PACKAGES")\n'
        'if packages:\n    sys.path.insert(0, packages)\n', encoding="utf-8")
    binaries = application / "bin"
    binaries.mkdir(exist_ok=True)
    ffmpeg = shutil.which("ffmpeg")
    if not ffmpeg:
        raise RuntimeError("构建机缺少 ffmpeg；请准备 ffmpeg 与 ffprobe 后重新构建")
    for name in ("ffmpeg.exe", "ffprobe.exe"):
        copy_changed(Path(ffmpeg).parent / name, binaries / name)
    requirements = ROOT / "ops/desktop/runtime-requirements.txt"
    if args.prepare_only:
        print("只完成资源准备，尚未安装依赖，不是可用绿色版。", flush=True)
        return
    environment = dict(os.environ, PYTHONUTF8="1", PIP_DISABLE_PIP_VERSION_CHECK="1")
    if not args.reuse_runtime:
        subprocess.run([sys.executable, "-m", "pip", "install", "--no-compile", "--timeout", "120", "--retries", "4", "--target", str(runtime / "Lib/site-packages"),
                        "--upgrade", "--only-binary=:all:", "-r", str(requirements), str(ROOT) + "[desktop]"], env=environment, check=True)
    if not args.reuse_runtime:
        subprocess.run([sys.executable, "-m", "pip", "install", "--no-compile", "--timeout", "120", "--retries", "4",
                        "--target", str(agent_packages), "--upgrade", "--only-binary=:all:", str(ROOT) + "[agent]"],
                       env=environment, check=True)
    for name in ("core", "agent", "desktop", "docs"):
        shutil.copytree(ROOT / name, project / name, ignore=ignored, dirs_exist_ok=True, copy_function=copy_changed)
    shutil.copy2(ROOT / "desktop/main.cjs", application / "main.cjs")
    (CACHE / "build-check-webui").mkdir(parents=True, exist_ok=True)
    check_environment = {**environment, "DATA_DIR": str(CACHE / "build-check-webui"), "OFFLINE_MODE": "true",
                         "HF_HUB_OFFLINE": "1", "RAG_EMBEDDING_ENGINE": "openai", "FROM_INIT_PY": "true",
                         "USE_SLIM_DOCKER": "true",
                         "CORS_ALLOW_ORIGIN": "http://127.0.0.1",
                         "STATIC_DIR": str(CACHE / "build-check-webui/static"), "WEBUI_SECRET_KEY": "0" * 64,
                         "MEDIA_FACTORY_HOME": str(CACHE / "gateway-check"),
                         "MEDIA_FACTORY_AGENT_DATABASE": str(CACHE / "gateway-check/agent.sqlite")}
    subprocess.run([str(runtime / "python.exe"), "-c", "import open_webui.main"],
                   cwd=project, env=check_environment, check=True)
    agent_environment = {**check_environment, "MEDIA_FACTORY_AGENT_PACKAGES": str(agent_packages)}
    subprocess.run([str(runtime / "python.exe"), "-c",
                    "import desktop.gateway; import core.mcp.finance.server; import core.mcp.language_learning.server; "
                    "import core.mcp.anime.__main__; import core.mcp.publishing.server"],
                   cwd=project, env=agent_environment, check=True)
    with (output / "依赖版本.txt").open("w", encoding="utf-8") as versions:
        for label, version_environment in (("界面依赖", check_environment), ("Agent 依赖", agent_environment)):
            versions.write(label + "\n")
            versions.flush()
            subprocess.run([str(runtime / "python.exe"), "-c",
                "import importlib.metadata as m; print(*(name+'=='+m.version(name) for name in "
                "sorted({d.metadata['Name'] for d in m.distributions()})), sep=chr(10))"],
                stdout=versions, env=version_environment, check=True)
    (output / "构建信息.json").write_text(json.dumps({"electron": version, "python": "3.12.10", "open_webui": "0.12.3",
        "built_at": datetime.now(timezone.utc).isoformat(), "agent_dependencies": "resources/app/agent-packages",
        "entry": "MediaFactory.exe", "dependencies_verified": True}, ensure_ascii=False, indent=2), encoding="utf-8")
    shutil.copy2(ROOT / "desktop/README.md", output / "使用说明.md")
    if not reuse_electron:
        (output / "electron.exe").replace(executable)
    (output / "MediaFactory.incomplete.exe").unlink(missing_ok=True)
    print("绿色版构建完成：" + str(executable), flush=True)


if __name__ == "__main__":
    main()
