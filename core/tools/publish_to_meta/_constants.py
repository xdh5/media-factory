"""发布到 Facebook / Instagram Reels 常量。"""

from pathlib import Path

from dotenv import load_dotenv

META_GRAPH_VERSION = "v21.0"
FACEBOOK_GRAPH_BASE = f"https://graph.facebook.com/{META_GRAPH_VERSION}"
INSTAGRAM_GRAPH_BASE = f"https://graph.instagram.com/{META_GRAPH_VERSION}"
META_REQUEST_TIMEOUT_SECONDS = 60
META_UPLOAD_TIMEOUT_SECONDS = 600
INSTAGRAM_CONTAINER_POLL_SECONDS = 5
INSTAGRAM_CONTAINER_TIMEOUT_SECONDS = 600
META_PLATFORMS = ("facebook", "instagram")

ACCOUNT_ID_PATTERN = r"^[a-z][a-z0-9_]{0,63}$"
FACEBOOK_PAGE_ID_SUFFIX = "_FACEBOOK_PAGE_ID"
FACEBOOK_PAGE_ACCESS_TOKEN_SUFFIX = "_FACEBOOK_PAGE_ACCESS_TOKEN"
INSTAGRAM_USER_ID_SUFFIX = "_INSTAGRAM_USER_ID"

R2_REGION = "auto"
R2_UPLOAD_TIMEOUT_SECONDS = 120
R2_REQUIRED_ENV = (
    "R2_ACCOUNT_ID",
    "R2_ACCESS_KEY_ID",
    "R2_SECRET_ACCESS_KEY",
    "R2_BUCKET",
    "R2_PUBLIC_BASE_URL",
)


def load_project_env() -> None:
    for candidate in Path(__file__).resolve().parents:
        if (candidate / "AGENTS.md").is_file():
            load_dotenv(candidate / ".env", override=True)
            return
    load_dotenv(override=True)
