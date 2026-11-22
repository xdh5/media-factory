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


async def check_accounts(publish_date: str) -> dict:
    """仅核验本次语言生产或补发所需的官方账号。"""
    from workflows.language_learning.tools.packs import language_learning_get_automation_plan
    from tools.publish_media.accounts import resolve_account_group

    plan = await asyncio.to_thread(language_learning_get_automation_plan, publish_date)
    targets = plan["publish_targets"] if plan["should_generate"] else plan["pending_targets"]
    if not targets:
        return {"status": "skipped", "reason": "没有待生产或待发布内容"}
    await asyncio.to_thread(resolve_account_group, "chinese", "language_learning", targets)
    print("**全部账号已登录，开始发布**", flush=True)
    return {"status": "ready", "platforms": targets}


async def produce_day(publish_date: str) -> dict:
    """领取词包并交付全部语言版本，失败时归还未使用词包。"""
    import os
    from tools.paths import PROJECT_ROOT
    from workflows.language_learning.production import run
    from workflows.language_learning.tools.packs import language_learning_get_automation_plan, language_learning_release_pack

    plan = await asyncio.to_thread(language_learning_get_automation_plan, publish_date)
    if not plan["should_generate"]:
        return {"status": "skipped", "reason": plan["skip_reason"]}
    work_dir = PROJECT_ROOT / "cache/github_actions/daily" / publish_date
    work_dir.mkdir(parents=True, exist_ok=True)
    os.environ["DASHSCOPE_BUSINESS_LINE"] = "language_learning"
    try:
        result = await run(publish_date, work_dir, plan, production_source="github_workflow")
        remaining = await asyncio.to_thread(language_learning_get_automation_plan, publish_date)
        if remaining["should_generate"]:
            raise RuntimeError(f"语言成片尚未补齐：{remaining['pending_outputs']}")
        return result
    except BaseException:
        await asyncio.to_thread(language_learning_release_pack, publish_date)
        raise


async def publish_day(publish_date: str) -> dict:
    """检查成片完整性后预约尚未发布的平台。"""
    from workflows.language_learning.tools.packs import language_learning_get_automation_plan

    plan = await asyncio.to_thread(language_learning_get_automation_plan, publish_date)
    if plan["should_generate"]:
        raise RuntimeError(f"语言成片尚未补齐：{plan['pending_outputs']}")
    if not plan["pending_targets"]:
        return {"status": "skipped", "reason": "目标平台均已有发布记录"}
    run_id = plan["existing_run_id"] or f"run-{publish_date.replace('-', '')}"
    return await schedule_publication(run_id, targets=plan["pending_targets"])
