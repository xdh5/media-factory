"""收集财经文案：下载用户给出的抖音链接，转写后写入文案库。"""

from __future__ import annotations

import time

from ..infrastructure.gateways import runner_submit_task
from ..services.collect_copy import CACHE_ROOT, collect_copy
from .common import _map_error


def finance_start_collect_copy(share_text: str, collection_name: str) -> dict:
    """收集一条抖音分享链接里的财经文案。

    立即返回 task_path，用 finance_poll_task 轮询至 done=true。
    collection_name 目前只接受“财经”。
    """
    try:
        run_id = f"run-{time.time_ns()}"
        cache_dir = CACHE_ROOT / run_id

        def _work() -> dict:
            return collect_copy(
                share_text,
                cache_dir,
                collection_name=collection_name,
            )

        started = runner_submit_task(
            cache_dir=cache_dir,
            run_id=run_id,
            step="collect_finance_copy",
            fn=_work,
        )
        return {**started, "poll_tool": "finance_poll_task"}
    except Exception as exc:
        raise _map_error(exc) from exc
