"""限制同一工作区的发布并发，并隔离账号与浏览器会话。"""

from contextlib import ExitStack, contextmanager
from hashlib import sha256
import time

from filelock import FileLock, Timeout

from tools.paths import PROJECT_CACHE_ROOT

MAX_CONCURRENT_PUBLICATIONS = 4
LOCK_ROOT = PROJECT_CACHE_ROOT / "publishing" / "target-locks"
BROWSER_PUBLISH_LOCK = "browser:publisher"


def publication_lock(key: str) -> FileLock:
    LOCK_ROOT.mkdir(parents=True, exist_ok=True)
    filename = sha256(key.encode()).hexdigest()
    return FileLock(LOCK_ROOT / f"{filename}.lock")


def publication_lock_keys(route: dict) -> tuple[str, ...]:
    """浏览器 CLI 的日志回执与交互文件共用通道。"""
    account = f"account:{route['platform']}:{route['platform_account_id']}"
    if route["connector"] == "media-publisher":
        return account, BROWSER_PUBLISH_LOCK
    return (account,)


@contextmanager
def publication_slot(keys: tuple[str, ...]):
    LOCK_ROOT.mkdir(parents=True, exist_ok=True)
    with ExitStack() as locks:
        for key in sorted(keys):
            locks.enter_context(publication_lock(key))
        while True:
            for index in range(MAX_CONCURRENT_PUBLICATIONS):
                slot = FileLock(LOCK_ROOT / f"slot-{index}.lock")
                try:
                    slot.acquire(timeout=0)
                except Timeout:
                    continue
                locks.callback(slot.release)
                yield
                return
            time.sleep(0.1)
