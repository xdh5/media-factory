"""按日期串行生产；财经和语言成片交付 R2。"""

from __future__ import annotations

import os
from datetime import date, datetime
from pathlib import Path
from zoneinfo import ZoneInfo

from ._dates import compute_next_week_dates
from ._shared import (
    PROJECT_ROOT,
)
from .finance import run as run_finance
from ._mcp import ProjectMCP
from .language_learning import (
    generate_cards,
    generate_videos,
    generate_words,
    upload_handoff,
)

async def _run_language_produce(publish_date: str, work_dir: Path, plan: dict) -> dict:
    state_path = work_dir / "language-learning-state.json"
    handoff_dir = work_dir / "handoff"
    diagnostics_dir = work_dir / "diagnostics"

    modes = list(dict.fromkeys(item["learning_mode"] for item in plan["pending_outputs"]))
    await generate_words("", modes, state_path, publish_date,
                         pending_outputs=plan["pending_outputs"], completed_outputs=plan["completed_outputs"])
    await generate_cards(state_path, diagnostics_dir)
    await generate_videos(state_path, handoff_dir)
    result = await upload_handoff(handoff_dir)
    return result


async def run_day(
    publish_date: str,
    *,
    cache_scope: str = "daily",
    finance_only: bool = False,
) -> dict:
    planned_date = date.fromisoformat(publish_date)
    today = datetime.now(ZoneInfo("Asia/Shanghai")).date()
    if planned_date < today:
        reason = f"计划发布日期 {publish_date} 早于北京时间当天 {today.isoformat()}，正常跳过"
        print(f"[{publish_date}] {reason}", flush=True)
        return {
            "publish_date": publish_date,
            "finance": {"status": "skipped", "reason": reason},
            "language": {"status": "skipped", "reason": reason},
        }

    work_dir = PROJECT_ROOT / "cache" / "github_actions" / cache_scope / publish_date
    work_dir.mkdir(parents=True, exist_ok=True)
    results: dict = {"publish_date": publish_date, "finance": {}, "language": {}}

    async with ProjectMCP("core.mcp.finance", PROJECT_ROOT) as finance_mcp:
        finance_preflight = await finance_mcp.call(
            "finance_get_automation_plan",
            {"publish_date": publish_date},
        )
    if finance_preflight["should_generate"]:
        os.environ["DASHSCOPE_BUSINESS_LINE"] = "finance"
        produced, failed = [], []
        for content_part in finance_preflight["pending_content_parts"]:
            try:
                print(f"[{publish_date}] 开始财经生产 part={content_part}", flush=True)
                finance_result = await run_finance(
                    publish_date=publish_date,
                    content_part=int(content_part),
                )
                produced.append({
                    "content_part": int(content_part),
                    "run_id": str(finance_result["manifest"]["run_id"]),
                })
            except Exception as exc:
                failed.append({"content_part": int(content_part), "error": str(exc)})
        success = not failed
        results["finance"] = {
            "status": "produced" if success else ("partially_produced" if produced else "produce_failed"),
            "produced": produced,
            "failed": failed,
        }
    else:
        results["finance"] = {
            "status": "skipped",
            "reason": finance_preflight["skip_reason"],
        }

    async with ProjectMCP("core.mcp.finance", PROJECT_ROOT) as finance_mcp:
        remaining = await finance_mcp.call("finance_get_automation_plan", {"publish_date": publish_date})
    if remaining["should_generate"]:
        results["finance"]["status"] = "produce_failed"
        results["finance"]["pending_content_parts"] = remaining["pending_content_parts"]
        print(f"[{publish_date}] 财经仍有缺失分片：{remaining['pending_content_parts']}", flush=True)

    if finance_only:
        results["language"] = {"status": "skipped", "reason": "本次仅补齐财经成片"}
        return results

    async with ProjectMCP("core.mcp.language_learning", PROJECT_ROOT) as language_mcp:
        lang_preflight = await language_mcp.call(
            "language_learning_get_automation_plan",
            {"publish_date": publish_date},
        )
    if not lang_preflight["should_generate"]:
        results["language"] = {"status": "skipped", "reason": lang_preflight["skip_reason"]}
        return results

    try:
        print(f"[{publish_date}] 开始语言生产", flush=True)
        os.environ["DASHSCOPE_BUSINESS_LINE"] = "language_learning"
        upload_result = await _run_language_produce(publish_date, work_dir, lang_preflight)
        run_id = str(upload_result["run_id"])
        results["language"] = {"status": "produced", "run_id": run_id}
    except Exception as exc:
        results["language"] = {"status": "produce_failed", "error": str(exc)}

    async with ProjectMCP("core.mcp.language_learning", PROJECT_ROOT) as language_mcp:
        remaining = await language_mcp.call("language_learning_get_automation_plan", {"publish_date": publish_date})
        if remaining["should_generate"]:
            await language_mcp.call("language_learning_release_pack", {"publish_date": publish_date})
    if remaining["should_generate"]:
        results["language"]["status"] = "produce_failed"
        results["language"]["pending_outputs"] = remaining["pending_outputs"]

    return results


async def run_week(week_start: str = "") -> dict:
    dates = compute_next_week_dates(week_start)
    day_results = []
    for publish_date in dates:
        day_results.append(await run_day(publish_date, cache_scope="weekly"))
    return {"dates": dates, "days": day_results}
