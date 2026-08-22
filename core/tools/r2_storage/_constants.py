"""Cloudflare R2 对象存储常量。"""

from pathlib import Path

from dotenv import load_dotenv

R2_REGION = "auto"
R2_UPLOAD_TIMEOUT_SECONDS = 120
R2_DOWNLOAD_TIMEOUT_SECONDS = 300
R2_REQUIRED_ENV = (
    "R2_ACCOUNT_ID",
    "R2_ACCESS_KEY_ID",
    "R2_SECRET_ACCESS_KEY",
    "R2_BUCKET",
    "R2_PUBLIC_BASE_URL",
)


def load_project_env() -> None:
    for candidate in Path(__file__).resolve().parents:
        if any((candidate / name).is_file() for name in ("AGENTS.md", "agents.md")):
            load_dotenv(candidate / ".env", override=True)
            return
    load_dotenv(override=True)
