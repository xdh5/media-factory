"""Instagram Graph API 发布常量。"""

from pathlib import Path

from dotenv import load_dotenv

META_GRAPH_API_BASE_URL = "https://graph.facebook.com"
META_GRAPH_API_VERSION_ENV = "META_GRAPH_API_VERSION"
DEFAULT_META_GRAPH_API_VERSION = "v23.0"
INSTAGRAM_USER_ID_ENV = "INSTAGRAM_USER_ID"
INSTAGRAM_ACCESS_TOKEN_ENV = "INSTAGRAM_ACCESS_TOKEN"
FACEBOOK_PAGE_ACCESS_TOKEN_ENV = "FACEBOOK_PAGE_ACCESS_TOKEN"
INSTAGRAM_ACCOUNT_TITLE_ENV = "INSTAGRAM_ACCOUNT_TITLE"
INSTAGRAM_USERNAME_ENV = "INSTAGRAM_USERNAME"
REQUEST_TIMEOUT_SECONDS = 120
STATUS_POLL_INTERVAL_SECONDS = 5
STATUS_TIMEOUT_SECONDS = 600
SUCCESS_STATUS_CODES = frozenset({"FINISHED", "PUBLISHED"})
FAILURE_STATUS_CODES = frozenset({"ERROR", "EXPIRED"})


def load_project_env() -> None:
    for candidate in Path(__file__).resolve().parents:
        if any((candidate / name).is_file() for name in ("AGENTS.md", "agents.md")):
            load_dotenv(candidate / ".env", override=True)
            return
    load_dotenv(override=True)
