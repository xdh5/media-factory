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
DESKTOP_SOURCE = ROOT / "apps" / "desktop"


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


def copy_publisher_dependencies(publisher, destination):
    """只打包运行依赖和发布器使用的 Electron。"""
    packages = json.loads((publisher / "package-lock.json").read_text(encoding="utf-8"))["packages"]
    for name, package in packages.items():
        if not name.startswith("node_modules/"):
            continue
        if package.get("dev") and name != "node_modules/electron":
            continue
        source = publisher / name
        if package.get("optional") and not source.is_dir():
            continue
        shutil.copytree(source, destination / name,
                        ignore=shutil.ignore_patterns("node_modules", ".cache", "__pycache__"),
                        dirs_exist_ok=True, copy_function=copy_changed)


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
        shutil.copy2(DESKTOP_SOURCE / name, application / name)
    # 运行目录只交付发布器资源，Python 业务代码通过 uv 安装。
    for legacy in (application / "project", application / "agent-packages"):
        if legacy.exists():
            legacy.resolve().relative_to(output)
            shutil.rmtree(legacy)
    project = application / "services"
    project.mkdir(exist_ok=True)
    ignored = shutil.ignore_patterns(".git", "node_modules", "__pycache__", ".env", "data", "cache", "*.sqlite*", "*.db", "*.log", "client_secret*.json", "*token.json")
    publisher = ROOT / "integrations/media-publisher"
    if not (publisher / "node_modules/electron/dist/electron.exe").is_file() or not (publisher / "dist/electron/main.js").is_file():
        raise RuntimeError("构建机需要先在 integrations/media-publisher 执行 npm ci 与 npm run build:dir")
    for integration, directories, files in (
        ("media-publisher", ("dist/electron",), ("LICENSE", "package.json")),
    ):
        source = ROOT / "integrations" / integration
        destination = project / "integrations" / integration
        for name in directories:
            shutil.copytree(source / name, destination / name, ignore=ignored,
                            dirs_exist_ok=True, copy_function=copy_changed)
        for name in files:
            copy_changed(source / name, destination / name)
    copy_publisher_dependencies(publisher, project / "integrations/media-publisher")
    for name in ("LICENSE", ".env.example"):
        shutil.copy2(ROOT / name, project / name)
    runtime = application / "python"
    agent_runtime = application / "agent-python"
    python_archive = download("https://www.python.org/ftp/python/3.12.10/python-3.12.10-embed-amd64.zip", "python-3.12.10-embed-amd64.zip")
    for environment_root in (runtime, agent_runtime):
        environment_root.mkdir(exist_ok=True)
        if not args.reuse_runtime or not (environment_root / "python.exe").is_file():
            with zipfile.ZipFile(python_archive) as source:
                source.extractall(environment_root)
        (environment_root / "python312._pth").write_text(
            "python312.zip\n.\nLib/site-packages\nimport site\n", encoding="utf-8")
        (environment_root / "Lib/site-packages").mkdir(parents=True, exist_ok=True)
        (environment_root / "Lib/site-packages/sitecustomize.py").unlink(missing_ok=True)
    binaries = application / "bin"
    binaries.mkdir(exist_ok=True)
    ffmpeg = shutil.which("ffmpeg")
    if not ffmpeg:
        raise RuntimeError("构建机缺少 ffmpeg；请准备 ffmpeg 与 ffprobe 后重新构建")
    for name in ("ffmpeg.exe", "ffprobe.exe"):
        copy_changed(Path(ffmpeg).parent / name, binaries / name)
    if args.prepare_only:
        print("只完成资源准备，尚未安装依赖，不是可用绿色版。", flush=True)
        return
    environment = dict(os.environ, PYTHONUTF8="1")
    packages = [str(ROOT),
                str(ROOT / "integrations/media-publisher/python")]
    dependency_identity = hashlib.sha256((ROOT / "uv.lock").read_bytes()).hexdigest()
    for extra, environment_root in (("desktop", runtime), ("agent", agent_runtime)):
        requirements = CACHE / f"{extra}-requirements.txt"
        dependency_marker = environment_root / "dependency-lock.txt"
        if not args.reuse_runtime or not dependency_marker.is_file() or dependency_marker.read_text() != dependency_identity:
            subprocess.run(["uv", "export", "--locked", "--no-dev", "--no-emit-workspace",
                            "--extra", extra, "--output-file", str(requirements), "--quiet"],
                           cwd=ROOT, env=environment, check=True)
            subprocess.run(["uv", "pip", "sync", "--python", str(environment_root / "python.exe"),
                            "--only-binary", ":all:", "--require-hashes", str(requirements)],
                           cwd=ROOT, env=environment, check=True)
            dependency_marker.write_text(dependency_identity, encoding="utf-8")
        subprocess.run(["uv", "pip", "install", "--python", str(environment_root / "python.exe"),
                        "--no-deps", "--reinstall", *packages], cwd=ROOT, env=environment, check=True)
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
    agent_environment = {**check_environment, "MEDIA_FACTORY_WORKSPACE": str(CACHE / "gateway-check/workspace")}
    subprocess.run([str(agent_runtime / "python.exe"), "-c",
                    "import desktop.gateway; import media_factory_mcp.finance.server; import media_factory_mcp.language_learning.server; "
                    "import media_factory_mcp.anime.__main__; import media_factory_mcp.publishing.server"],
                   cwd=project, env=agent_environment, check=True)
    with (output / "依赖版本.txt").open("w", encoding="utf-8") as versions:
        for label, environment_root, version_environment in (("界面依赖", runtime, check_environment), ("Agent 依赖", agent_runtime, agent_environment)):
            versions.write(label + "\n")
            versions.flush()
            subprocess.run([str(environment_root / "python.exe"), "-c",
                "import importlib.metadata as m; print(*(name+'=='+m.version(name) for name in "
                "sorted({d.metadata['Name'] for d in m.distributions()})), sep=chr(10))"],
                stdout=versions, env=version_environment, check=True)
    (output / "构建信息.json").write_text(json.dumps({"electron": version, "python": "3.12.10", "open_webui": "0.12.3",
        "built_at": datetime.now(timezone.utc).isoformat(), "agent_runtime": "resources/app/agent-python",
        "entry": "MediaFactory.exe", "dependencies_verified": True}, ensure_ascii=False, indent=2), encoding="utf-8")
    shutil.copy2(DESKTOP_SOURCE / "README.md", output / "使用说明.md")
    if not reuse_electron:
        (output / "electron.exe").replace(executable)
    (output / "MediaFactory.incomplete.exe").unlink(missing_ok=True)
    print("绿色版构建完成：" + str(executable), flush=True)


if __name__ == "__main__":
    main()
