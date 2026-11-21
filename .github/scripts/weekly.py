"""按日期串行生产；财经和语言成片交付 R2。"""

from __future__ import annotations

import asyncio
import os
from datetime import date, datetime
from zoneinfo import ZoneInfo

from tools.paths import (
    PROJECT_ROOT,
)
from .finance import run as run_finance
from workflows.finance.tools.drafts import finance_get_automation_plan
from workflows.language_learning.tools.packs import (
    language_learning_get_automation_plan, language_learning_release_pack,
)
from workflows.language_learning.production import run as _run_language_produce


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

    finance_preflight = await asyncio.to_thread(finance_get_automation_plan, publish_date)
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

    remaining = await asyncio.to_thread(finance_get_automation_plan, publish_date)
    if remaining["should_generate"]:
        results["finance"]["status"] = "produce_failed"
        results["finance"]["pending_content_parts"] = remaining["pending_content_parts"]
        print(f"[{publish_date}] 财经仍有缺失分片：{remaining['pending_content_parts']}", flush=True)

    if finance_only:
        results["language"] = {"status": "skipped", "reason": "本次仅补齐财经成片"}
        return results

    lang_preflight = await asyncio.to_thread(language_learning_get_automation_plan, publish_date)
    if not lang_preflight["should_generate"]:
        results["language"] = {"status": "skipped", "reason": lang_preflight["skip_reason"]}
        return results

    try:
        print(f"[{publish_date}] 开始语言生产", flush=True)
        os.environ["DASHSCOPE_BUSINESS_LINE"] = "language_learning"
        upload_result = await _run_language_produce(publish_date, work_dir, lang_preflight, production_source="github_workflow")
        run_id = str(upload_result["run_id"])
        results["language"] = {"status": "produced", "run_id": run_id}
    except Exception as exc:
        results["language"] = {"status": "produce_failed", "error": str(exc)}

    remaining = await asyncio.to_thread(language_learning_get_automation_plan, publish_date)
    if remaining["should_generate"]:
        await asyncio.to_thread(language_learning_release_pack, publish_date)
        results["language"]["status"] = "produce_failed"
        results["language"]["pending_outputs"] = remaining["pending_outputs"]

    return results
