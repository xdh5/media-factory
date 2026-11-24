"""本机与云端开发环境的能力配置。"""

import os

from dotenv import dotenv_values

from tools.paths import PROJECT_ROOT


def publishing_enabled() -> bool:
    profile = os.getenv("MEDIA_FACTORY_PROFILE") or dotenv_values(PROJECT_ROOT / ".env").get("MEDIA_FACTORY_PROFILE", "local")
    return profile != "codex-cloud"
