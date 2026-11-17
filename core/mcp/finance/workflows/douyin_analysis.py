"""财经抖音作品复盘的后台入口。"""

from ..config.settings import PROJECT_CACHE_ROOT
from ..errors import WorkflowStepError
from ..infrastructure.gateways import runner_submit_task
from ..services.douyin_performance import RANKING_METRICS, gather_douyin_performance


def finance_start_douyin_analysis(
    days: int = 90,
    sample_size: int = 12,
    rank_by: str = "view_count",
    minimum_age_hours: int = 48,
) -> dict:
    """只读采集 finance 抖音公开作品指标，并关联数据库定稿及黄金钩子。用 finance_get_task 查询结果，按返回的提示词由宿主分析。"""
    if not 1 <= days <= 180 or not 3 <= sample_size <= 30:
        raise WorkflowStepError("统计天数须在 1 至 180 之间，文案样本数须在 3 至 30 之间")
    if rank_by not in RANKING_METRICS:
        raise WorkflowStepError(f"排序指标必须为 {', '.join(RANKING_METRICS)} 之一")
    if minimum_age_hours < 0:
        raise WorkflowStepError("最短发布小时数必须大于等于 0")

    def work(progress):
        return gather_douyin_performance(days, sample_size, rank_by, minimum_age_hours, progress)

    result = runner_submit_task(
        cache_dir=PROJECT_CACHE_ROOT / "finance" / "douyin-analysis",
        run_id=f"{days}-{sample_size}-{rank_by}-{minimum_age_hours}",
        step="douyin_analysis",
        fn=work,
    )
    return {**result, "poll_tool": "finance_get_task"}
