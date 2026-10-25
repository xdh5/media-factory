"""共享后台发布批次工具。"""

from core.tools.publish_media.content import normalize_platforms, normalize_publish_date
from ..infrastructure.batch_jobs import launch_batch, read_batch, batch_summary


def publishing_start_batch(
    business_line: str, account_group: str, platforms: list[str],
    publications: list[dict], prepare_only: bool = False,
) -> dict:
    """一次提交多日期发布，后台独立执行，不保持模型轮询。先核验全部账号并向用户报告通过后调用。

    publications 每项包含 publish_date，可选 content_kind、production_id、publish_mode、publish_at、publish_at_by_platform。
    财经省略时间遵守14点和18点规则；韩语传明确的16点预约时间。prepare_only只准备成片，不上传或发布。
    """
    if not account_group or any(character not in "abcdefghijklmnopqrstuvwxyzABCDEFGHIJKLMNOPQRSTUVWXYZ0123456789_-" for character in account_group):
        raise ValueError("账号组必须是有效的账号组标识")
    if not publications:
        raise ValueError("发布批次不能为空")
    keys = {"publish_date", "content_kind", "production_id", "publish_mode", "publish_at", "publish_at_by_platform"}
    normalized = []
    for publication in publications:
        unknown = set(publication) - keys
        if unknown:
            raise ValueError(f"不支持的发布参数：{', '.join(sorted(unknown))}")
        normalized.append({**publication, "publish_date": normalize_publish_date(publication.get("publish_date"))})
    return launch_batch({"business_line": business_line, "account_group": account_group,
                         "platforms": normalize_platforms(platforms), "publications": normalized,
                         "prepare_only": prepare_only})


def publishing_batch_status(job_path: str, detailed: bool = False) -> dict:
    """按需查询独立后台批次，普通等待期间不要循环调用。默认只返回完成日期、计数和异常；完整日志留本地。"""
    data = read_batch(job_path)
    return data if detailed else batch_summary(data)
