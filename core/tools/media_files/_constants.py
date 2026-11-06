"""成片和图片文件存储常量。"""

from dotenv import load_dotenv

from core.paths import PROJECT_ROOT

R2_REGION = "auto"
R2_UPLOAD_TIMEOUT_SECONDS = 120
R2_DOWNLOAD_TIMEOUT_SECONDS = 30
R2_REQUIRED_ENV = (
    "R2_ACCOUNT_ID",
    "R2_ACCESS_KEY_ID",
    "R2_SECRET_ACCESS_KEY",
    "R2_BUCKET",
    "R2_PUBLIC_BASE_URL",
)


def load_project_env() -> None:
    load_dotenv(PROJECT_ROOT / ".env", override=True)
