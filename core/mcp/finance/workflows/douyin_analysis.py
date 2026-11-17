"""财经抖音公开作品取数的后台入口。"""

from ..config.settings import PROJECT_CACHE_ROOT
from ..infrastructure.gateways import runner_submit_task
from ..services.douyin_performance import gather_douyin_works


def finance_start_douyin_analysis() -> dict:
    """只读采集 finance 抖音公开作品、平台原始指标和关联的 Cloudflare D1 定稿。用 finance_get_task 读取结果。"""
    result = runner_submit_task(
        cache_dir=PROJECT_CACHE_ROOT / "finance" / "douyin-analysis",
        run_id="finance-douyin-works",
        step="collect_douyin_works",
        fn=gather_douyin_works,
    )
    return {**result, "poll_tool": "finance_get_task"}
