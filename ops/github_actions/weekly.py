"""按计划发布日期串行生产财经、语言并发布语言。"""

from __future__ import annotations

import asyncio
import os
import time
from datetime import date, datetime, timedelta
from pathlib import Path
from zoneinfo import ZoneInfo

from ._shared import (
    LANGUAGE_PUBLISH_TARGETS,
    PROJECT_ROOT,
    daily_production_preflight,
    restore_finance_image_library,
)
from .finance import run as run_finance
from .language_learning import (
    generate_cards,
    generate_videos,
    generate_words,
    schedule_publication,
    upload_failed_subject_sheets,
    upload_handoff,
)
from .telegram import notify_business_result


def compute_next_week_dates(week_start: str = "") -> list[str]:
    """计算下周周一至周日的计划发布日期；留空时按北京时间推算。"""
    text = str(week_start or "").strip()
    if text:
        monday = date.fromisoformat(text)
    else:
        today = datetime.now(ZoneInfo("Asia/Shanghai")).date()
        if today.weekday() == 0:
            monday = today + timedelta(days=7)
        else:
            days_until_monday = (7 - today.weekday()) % 7
            monday = today + timedelta(days=days_until_monday)
    return [(monday + timedelta(days=offset)).isoformat() for offset in range(7)]


def inspect_day_health(publish_date: str) -> dict:
    """从 D1 检查某个计划发布日期的两条业务线是否完整。"""
    finance = daily_production_preflight("finance", publish_date)
    language = daily_production_preflight("language_learning", publish_date)
    finance_healthy = finance["github_output_count"] > 0
    language_healthy = (
        bool(language["existing_run_id"])
        and language["github_output_count"] > 0
        and not language["pending_targets"]
    )
    return {
        "publish_date": publish_date,
        "healthy": finance_healthy and language_healthy,
        "finance": {
            "healthy": finance_healthy,
            "output_count": finance["output_count"],
            "github_output_count": finance["github_output_count"],
        },
        "language": {
            "healthy": language_healthy,
            "output_count": language["output_count"],
            "github_output_count": language["github_output_count"],
            "pending_targets": language["pending_targets"],
        },
    }


def restore_finance_libraries() -> None:
    restore_finance_image_library("finance")
    restore_finance_image_library("finance_generated")


async def _run_language_produce(publish_date: str, work_dir: Path) -> dict:
    state_path = work_dir / "language-learning-state.json"
    handoff_dir = work_dir / "handoff"
    diagnostics_dir = work_dir / "diagnostics"
    diagnostics_dir.mkdir(parents=True, exist_ok=True)
    (diagnostics_dir / "diagnostics.json").write_text('{"status":"not_started"}\n', encoding="utf-8")

    await generate_words("", ["en-zh", "en-ko"], state_path, publish_date)
    await generate_cards(state_path, diagnostics_dir)
    await generate_videos(state_path, handoff_dir)
    result = upload_handoff(handoff_dir)
    try:
        upload_failed_subject_sheets(diagnostics_dir)
    except Exception:
        pass
    return result


async def _publish_language_with_retry(
    manifest_url: str,
    run_id: str,
    targets: list[str],
    *,
    max_attempts: int = 3,
) -> dict:
    last_error: Exception | None = None
    for attempt in range(1, max_attempts + 1):
        try:
            return await schedule_publication(manifest_url, run_id, targets=targets)
        except Exception as exc:
            last_error = exc
            if attempt < max_attempts:
                time.sleep(30 * attempt)
    assert last_error is not None
    raise last_error


def _manifest_url(run_id: str) -> str:
    base = os.getenv("R2_PUBLIC_BASE_URL", "").strip().rstrip("/")
    if not base:
        raise RuntimeError("缺少环境变量 R2_PUBLIC_BASE_URL")
    return f"{base}/runs/language_learning/{run_id}/r2-manifest.json"


async def run_day(publish_date: str, run_url: str = "", *, cache_scope: str = "daily") -> dict:
    work_dir = PROJECT_ROOT / "cache" / "github_actions" / cache_scope / publish_date
    work_dir.mkdir(parents=True, exist_ok=True)
    results: dict = {"publish_date": publish_date, "finance": {}, "language": {}}

    finance_preflight = daily_production_preflight("finance", publish_date)
    try:
        if finance_preflight["should_generate"]:
            os.environ["DASHSCOPE_BUSINESS_LINE"] = "finance"
            await run_finance(publish_date=publish_date)
            notify_business_result("财经生产", True, run_url)
            results["finance"] = {"status": "produced"}
        else:
            results["finance"] = {"status": "skipped", "reason": finance_preflight["skip_reason"]}
    except Exception as exc:
        notify_business_result("财经生产", False, run_url, str(exc))
        results["finance"] = {"status": "failed", "error": str(exc)}

    lang_preflight = daily_production_preflight("language_learning", publish_date)
    if not lang_preflight["should_generate"] and not lang_preflight["should_resume_publish"]:
        results["language"] = {"status": "skipped", "reason": lang_preflight["skip_reason"]}
        return results

    run_id = str(lang_preflight["existing_run_id"] or "")
    publish_targets = list(lang_preflight["pending_targets"])

    if lang_preflight["should_generate"]:
        try:
            os.environ["DASHSCOPE_BUSINESS_LINE"] = "language_learning"
            upload_result = await _run_language_produce(publish_date, work_dir)
            run_id = str(upload_result["run_id"])
            publish_targets = list(LANGUAGE_PUBLISH_TARGETS)
        except Exception as exc:
            notify_business_result("语言生产", False, run_url, str(exc))
            results["language"] = {"status": "produce_failed", "error": str(exc)}
            return results

    if not run_id:
        raise RuntimeError(f"{publish_date} 缺少可发布的 language_learning run_id")

    try:
        await _publish_language_with_retry(
            _manifest_url(run_id),
            run_id,
            publish_targets,
        )
        notify_business_result("语言发布", True, run_url)
        results["language"] = {"status": "published", "run_id": run_id}
    except Exception as exc:
        notify_business_result("语言发布", False, run_url, str(exc))
        results["language"] = {"status": "publish_failed", "error": str(exc)}

    return results


async def run_day_with_health_retry(
    publish_date: str,
    run_url: str = "",
    *,
    max_retries: int = 3,
    health_delay_seconds: int = 180,
) -> dict:
    """运行单日任务；每轮结束后延迟检查 D1，仅补偿缺失产品，最多重试三次。"""
    if max_retries < 0:
        raise ValueError("max_retries 不能小于 0")
    if health_delay_seconds < 0:
        raise ValueError("health_delay_seconds 不能小于 0")

    initial_health = inspect_day_health(publish_date)
    if initial_health["healthy"]:
        return {
            "publish_date": publish_date,
            "finance": {"status": "skipped", "reason": "D1 健康检查已完整"},
            "language": {"status": "skipped", "reason": "D1 健康检查已完整"},
            "health": initial_health,
            "attempts": [],
        }

    attempts = []
    for attempt in range(max_retries + 1):
        try:
            result = await run_day(publish_date, run_url, cache_scope="weekly")
        except Exception as exc:
            result = {
                "publish_date": publish_date,
                "finance": {"status": "unknown"},
                "language": {"status": "failed", "error": str(exc)},
            }
        if health_delay_seconds:
            await asyncio.sleep(health_delay_seconds)
        health = inspect_day_health(publish_date)
        attempts.append({"attempt": attempt + 1, "result": result, "health": health})
        if health["healthy"]:
            return {**result, "health": health, "attempts": attempts}
        if attempt < max_retries:
            print(
                f"{publish_date} 健康检查未通过，准备第 {attempt + 1} 次补偿：{health}",
                flush=True,
            )

    return {
        **attempts[-1]["result"],
        "health": attempts[-1]["health"],
        "attempts": attempts,
    }


async def run_week(week_start: str = "", run_url: str = "") -> dict:
    dates = compute_next_week_dates(week_start)
    restore_finance_libraries()
    day_results = []
    for publish_date in dates:
        day_results.append(await run_day_with_health_retry(publish_date, run_url))
    return {"dates": dates, "days": day_results}
