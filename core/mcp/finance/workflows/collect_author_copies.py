"""按作者名单抓取财经稿件。"""

from __future__ import annotations

import time

from ..infrastructure.gateways import runner_submit_task
from ..services.collect_copy import CACHE_ROOT
from ..services.collect_author_copies import collect_author_copies
from .common import _map_error


def finance_start_collect_author_copies(count: int) -> dict:
    """按当前作者人数平分抓取财经稿件。

    count 是要入库的总篇数。10 位作者、count 为 100 时，每人取 10 条最新且未入库的正常口播。
    整篇广告不入库，正文中的插入广告会删掉后再入库。
    立即返回 task_path，用 finance_poll_task 轮询至 done=true。
    """
    try:
        run_id = f"run-{time.time_ns()}"
        cache_dir = CACHE_ROOT / run_id

        def _work() -> dict:
            return collect_author_copies(count, cache_dir)

        started = runner_submit_task(
            cache_dir=cache_dir,
            run_id=run_id,
            step="collect_finance_author_copies",
            fn=_work,
        )
        return {**started, "poll_tool": "finance_poll_task"}
    except Exception as extra:
        raise _map_error(extra) from extra
