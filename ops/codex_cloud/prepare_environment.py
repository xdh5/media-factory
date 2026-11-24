"""在独立的 Codex Cloud 检出目录中配置制作环境。"""

import json
import os
from pathlib import Path
import shutil
import subprocess

from dotenv import dotenv_values, set_key

ROOT = Path(__file__).resolve().parents[2]


def main():
    if os.getenv("MEDIA_FACTORY_PROFILE") != "codex-cloud":
        raise SystemExit("请仅在云端设置 MEDIA_FACTORY_PROFILE=codex-cloud 后运行；本机无需执行")
    environment_file = ROOT / ".env"
    if environment_file.exists():
        raise SystemExit("云端配置需要没有 .env 的独立检出目录，避免覆盖本机配置")
    allowed = dotenv_values(ROOT / "ops/codex_cloud/environment.example")
    environment_file.write_text("# Codex Cloud 采集与制作配置。\n", encoding="utf-8")
    set_key(environment_file, "MEDIA_FACTORY_PROFILE", "codex-cloud")
    for key, default in allowed.items():
        value = os.getenv(key, default or "")
        if value:
            set_key(environment_file, key, value)
    # 只调整这份云端检出目录，本机发布技能和凭据不受影响。
    for name in ("publish-finance", "publish-korean", "publish-anime-youtube"):
        target = ROOT / ".agents/skills" / name
        if target.is_dir():
            shutil.rmtree(target)
    instructions = ROOT / "AGENTS.md"
    with instructions.open("a", encoding="utf-8") as stream:
        stream.write("\n## Codex Cloud 环境\n仅执行开发、采集和制作。不得上传、预约或发布，不得触发发布工作流，不得读取或补充发布账号凭据。\n")
    subprocess.run(["uv", "sync", "--locked", "--no-editable", "--no-dev", "--extra", "mcp"], cwd=ROOT, check=True)
    servers = {name: {"command": "uv", "args": ["run", "--locked", "--no-editable", "--no-dev", "--extra", "mcp", "python", "-m", f"media_factory_mcp.{name}"], "cwd": str(ROOT), "env": {"MEDIA_FACTORY_PROFILE": "codex-cloud", "MEDIA_FACTORY_WORKSPACE": str(ROOT)}} for name in ("finance", "language_learning", "anime")}
    (ROOT / ".mcp.json").write_text(json.dumps({"mcpServers": servers}, ensure_ascii=False, indent=2), encoding="utf-8")
    print("云端制作环境已配置，未启用发布服务。MCP 客户端请使用生成的服务配置。")


if __name__ == "__main__":
    main()
