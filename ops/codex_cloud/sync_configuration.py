"""同步云端制作配置，不读取或写入发布账号。"""

import os
from pathlib import Path

from dotenv import dotenv_values, set_key

ROOT = Path(__file__).resolve().parents[2]


def synchronize_configuration():
    """将部署变量更新到云端工作目录，兼容平台保留的变量名前缀。"""
    if os.getenv("MEDIA_FACTORY_PROFILE") != "codex-cloud":
        raise SystemExit("仅用于 Codex Cloud 制作环境")
    target = ROOT / ".env"
    if not target.exists():
        target.write_text("# Codex Cloud 采集与制作配置。\n", encoding="utf-8")
    if dotenv_values(target).get("MEDIA_FACTORY_PROFILE", "codex-cloud") != "codex-cloud":
        raise SystemExit("当前 .env 不属于云端制作环境")
    set_key(target, "MEDIA_FACTORY_PROFILE", "codex-cloud")
    aliases = {
        "CLOUDFLARE_API_TOKEN": "MEDIA_FACTORY_CLOUDFLARE_API_TOKEN",
        "AZURE_SPEECH_KEY": "MEDIA_FACTORY_AZURE_SPEECH_KEY",
        "AZURE_SPEECH_REGION": "MEDIA_FACTORY_AZURE_SPEECH_REGION",
    }
    for key, default in dotenv_values(ROOT / "ops/codex_cloud/environment.example").items():
        value = os.getenv(aliases.get(key, key)) or os.getenv(key)
        if value is None and key not in dotenv_values(target):
            value = default
        if value:
            set_key(target, key, value)
    print("云端制作变量已同步，未输出密钥")


if __name__ == "__main__":
    synchronize_configuration()
