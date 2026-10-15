"""宿主 Agent 提交文案审核结果及继续补抓的 MCP 接口。"""

import time

from ..infrastructure.gateways import runner_submit_task
from ..services.copy_review import submit_copy_reviews, load_review_context
from ..services.collect_author_copies import continue_collect_author_copies
from .common import _map_error


def finance_submit_copy_reviews(context_path: str, response_text: str) -> dict:
    """提交宿主校对及广告审核 JSON，正常稿件入库，广告登记排除。"""
    try:
        return submit_copy_reviews(context_path, response_text)
    except Exception as extra:
        raise _map_error(extra) from extra


def finance_start_continue_collect_author_copies(context_path: str) -> dict:
    """按原采集上下文补足作者配额，返回任务后轮询并继续宿主审核。"""
    try:
        path, context = load_review_context(context_path)
        if not context.get("authors"):
            raise ValueError("该上下文不是按作者抓取任务")
        started = runner_submit_task(
            cache_dir=path.parent, run_id=f"run-{time.time_ns()}",
            step="continue_collect_finance_author_copies",
            fn=lambda: continue_collect_author_copies(str(path)),
        )
        return {**started, "poll_tool": "finance_poll_task"}
    except Exception as extra:
        raise _map_error(extra) from extra
