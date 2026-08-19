"""后台任务约定。"""

from pathlib import Path

_PROJECT_ROOT = Path(__file__).resolve().parents[3]
PROJECT_ROOT = _PROJECT_ROOT
PROJECT_DATA_ROOT = _PROJECT_ROOT / "data"
DEFAULT_DATABASE_PATH = PROJECT_DATA_ROOT / "media_factory.sqlite3"
JOB_SCHEMA_VERSION = 1
JOB_HEARTBEAT_SECONDS = 10
WORKFLOW_ID_PATTERN = r"^[a-z][a-z0-9_]{0,63}$"
HANDLER_PATTERN = r"^[A-Za-z_][\w.]*:[A-Za-z_]\w*$"
JOB_ID_PATTERN = r"^job-[0-9a-f]{32}$"
PROCESS_MODULE = "core.tools.jobs"
JOB_EVENT_STREAM = "media-factory:job-events"
JOB_EVENT_STREAM_MAXLEN = 5000
JOB_WAIT_TIMEOUT_SECONDS = 180
JOB_WAIT_POLL_SECONDS = 0.4
