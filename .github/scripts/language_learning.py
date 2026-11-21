"""语言学习自动化入口与发布调度。"""
import asyncio

from tools.publish_media import publish_local_outputs
from tools.production_dates import publish_date_from_run_id


async def schedule_publication(
    run_id: str,
    *,
    targets: list[str] | None = None,
) -> dict:
    """调用发布工具，把 GitHub/R2 成片通过官方接口排到北京时间 16:00。"""
    publish_date = publish_date_from_run_id(run_id)
    publish_at = f"{publish_date}T16:00:00+08:00"
    supported_targets = ["youtube", "tiktok", "instagram", "facebook"]
    selected_targets = [
        str(item).strip().casefold()
        for item in (supported_targets if targets is None else targets)
        if str(item).strip()
    ]
    unknown = set(selected_targets) - set(supported_targets)
    if unknown:
        raise RuntimeError(f"不支持的语言学习发布平台：{', '.join(sorted(unknown))}")
    if not selected_targets:
        return {"success": True, "skipped": True, "reason": "该计划发布日期四个平台都已有发布记录"}
    result = await asyncio.to_thread(
        publish_local_outputs,
        business_line="language_learning",
        publish_date=publish_date,
        account_group="chinese",
        platforms=selected_targets,
        content_kind="en-zh",
        publish_mode="scheduled",
        publish_at=publish_at,
    )
    completed_channels = {
        str(item.get("record", {}).get("platform") or "").strip().casefold()
        for item in result.get("published") or []
    }
    completed_channels.update(
        str(item.get("platform") or "").strip().casefold()
        for item in result.get("skipped") or []
    )
    missing_channels = set(selected_targets) - completed_channels
    if missing_channels:
        raise RuntimeError(f"四平台排期返回不完整，缺少：{', '.join(sorted(missing_channels))}")
    return {"publish_at": publish_at, "run_id": run_id, **result}
