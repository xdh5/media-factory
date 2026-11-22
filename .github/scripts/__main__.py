"""GitHub Actions 视频创建命令行入口。"""

from __future__ import annotations

import argparse
import asyncio
import json
import os
from pathlib import Path


def main() -> None:
    parser = argparse.ArgumentParser(description="媒体工厂 GitHub Actions 视频创建")
    parser.add_argument(
        "workflow",
        choices=[
            "finance_preflight",
            "finance",
            "language_learning_preflight",
            "language_learning_publish",
            "weekly_plan",
            "finance_produce_day",
            "language_learning_account_check",
            "language_learning_produce_day",
            "language_learning_publish_day",
        ],
    )
    parser.add_argument("--run-id", default="")
    parser.add_argument("--targets", default="")
    parser.add_argument("--publish-date", default="")
    parser.add_argument("--publish-dates", default="")
    parser.add_argument("--default-days-ahead", type=int, choices=(0, 1), default=0)
    parser.add_argument("--week-start", default="")
    arguments = parser.parse_args()
    if arguments.workflow.startswith("language_learning"):
        os.environ["DASHSCOPE_BUSINESS_LINE"] = "language_learning"
    if arguments.workflow in {"finance_preflight", "language_learning_preflight"}:
        business_line = "finance" if arguments.workflow == "finance_preflight" else "language_learning"
        from ._dates import resolve_publish_date
        from workflows.finance.tools.drafts import finance_get_automation_plan
        from workflows.language_learning.tools.packs import language_learning_get_automation_plan

        publish_date = resolve_publish_date(arguments.publish_date, arguments.default_days_ahead)
        get_plan = finance_get_automation_plan if business_line == "finance" else language_learning_get_automation_plan
        payload = asyncio.run(asyncio.to_thread(get_plan, publish_date))
        output_path = os.getenv("GITHUB_OUTPUT", "").strip()
        if output_path:
            with Path(output_path).open("a", encoding="utf-8") as stream:
                stream.write(f"publish_date={payload['publish_date']}\n")
                stream.write(f"should_generate={str(payload['should_generate']).lower()}\n")
                if business_line == "language_learning":
                    stream.write(f"should_resume_publish={str(payload['should_resume_publish']).lower()}\n")
                    stream.write(f"existing_run_id={payload['existing_run_id']}\n")
                    stream.write(f"pending_targets={','.join(payload['pending_targets'])}\n")
                stream.write(f"skip_reason={payload['skip_reason']}\n")
    elif arguments.workflow == "finance":
        from .finance import run as run_finance

        result = asyncio.run(run_finance(publish_date=arguments.publish_date))
        payload = {"status": "succeeded", "run_id": result["manifest"]["run_id"], "r2": result["r2"]}
    elif arguments.workflow == "language_learning_publish":
        from .language_learning import schedule_publication

        targets = [item.strip() for item in arguments.targets.split(",") if item.strip()]
        payload = asyncio.run(
            schedule_publication(arguments.run_id, targets=targets or None)
        )
    elif arguments.workflow == "weekly_plan":
        from ._dates import compute_next_week_dates

        if arguments.publish_dates:
            from ._dates import resolve_publish_date
            if arguments.publish_date or arguments.week_start:
                parser.error("publish_dates 不能同时指定 publish_date 或 week_start")
            values = [value.strip() for value in arguments.publish_dates.split(",") if value.strip()]
            if not values:
                parser.error("publish_dates 必须包含至少一个日期")
            dates = list(dict.fromkeys(resolve_publish_date(value) for value in values))
        elif arguments.publish_date:
            from ._dates import resolve_publish_date
            dates = [resolve_publish_date(arguments.publish_date)]
        else:
            dates = compute_next_week_dates(arguments.week_start)
        payload = {"dates": dates}
        output_path = os.getenv("GITHUB_OUTPUT", "").strip()
        if output_path:
            with Path(output_path).open("a", encoding="utf-8") as stream:
                stream.write(f"dates_json={json.dumps(dates, ensure_ascii=False)}\n")
    elif arguments.workflow in {"finance_produce_day", "language_learning_account_check", "language_learning_produce_day", "language_learning_publish_day"}:
        from ._dates import resolve_publish_date
        from .finance import produce_day as produce_finance
        from .language_learning import check_accounts, produce_day as produce_language, publish_day

        handlers = {
            "finance_produce_day": produce_finance,
            "language_learning_account_check": check_accounts,
            "language_learning_produce_day": produce_language,
            "language_learning_publish_day": publish_day,
        }
        payload = asyncio.run(handlers[arguments.workflow](resolve_publish_date(arguments.publish_date)))
    print(json.dumps(payload, ensure_ascii=False))


if __name__ == "__main__":
    main()
