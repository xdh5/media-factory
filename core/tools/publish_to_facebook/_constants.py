"""Zernio Facebook 发布常量。"""

from pathlib import Path

from dotenv import load_dotenv

ZERNIO_API_BASE_URL = "https://zernio.com/api/v1"
ZERNIO_META_API_KEY_ENV = "zernio_api_key_meta"
FACEBOOK_ACCOUNT_ID_ENV = "LANGUAGE_LEARNING_FACEBOOK_ACCOUNT_ID"
FACEBOOK_REQUEST_TIMEOUT_SECONDS = 120
FACEBOOK_STATUS_POLL_INTERVAL_SECONDS = 2
FACEBOOK_STATUS_TIMEOUT_SECONDS = 180
FACEBOOK_SUCCESS_STATUSES = frozenset({"published", "success"})
FACEBOOK_FAILURE_STATUSES = frozenset({"failed", "cancelled", "canceled"})


def load_project_env() -> None:
    for candidate in Path(__file__).resolve().parents:
        if any((candidate / name).is_file() for name in ("AGENTS.md", "agents.md")):
            load_dotenv(candidate / ".env", override=True)
            return
    load_dotenv(override=True)
