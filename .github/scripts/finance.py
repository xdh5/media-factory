"""财经 GitHub Action：读取宿主定稿和分镜，搜索素材并制作成片。"""

from __future__ import annotations

async def run(publish_date: str = "", content_part: int = 1) -> dict:
    from workflows.finance.production import run as produce
    return await produce(publish_date, content_part, production_source="github_workflow")


async def produce_day(publish_date: str) -> dict:
    """补齐指定日期的财经分片，缺片或失败时令当前步骤失败。"""
    import asyncio
    from workflows.finance.tools.drafts import finance_get_automation_plan

    plan = await asyncio.to_thread(finance_get_automation_plan, publish_date)
    produced, failed = [], []
    for part in plan["pending_content_parts"]:
        try:
            print(f"[{publish_date}] 开始财经生产 part={part}", flush=True)
            result = await run(publish_date, int(part))
            produced.append({"content_part": int(part), "run_id": result["manifest"]["run_id"]})
        except Exception as exc:
            failed.append({"content_part": int(part), "error": str(exc)})
    remaining = await asyncio.to_thread(finance_get_automation_plan, publish_date)
    if failed or remaining["should_generate"]:
        raise RuntimeError(f"财经生产失败：{failed}；待补分片：{remaining['pending_content_parts']}")
    return {"publish_date": publish_date, "produced": produced, "status": "produced" if produced else "skipped"}
