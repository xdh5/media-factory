"""后台任务独立进程入口：python -m core.tools.jobs <database_path> <job_id>"""

from __future__ import annotations

import sys

from .jobs import execute_persisted_job


def main() -> int:
    if len(sys.argv) != 3:
        raise SystemExit("用法：python -m core.tools.jobs <database_path> <job_id>")
    execute_persisted_job(sys.argv[1], sys.argv[2])
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
