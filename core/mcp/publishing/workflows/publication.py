"""发布预览、执行与状态查询。"""

from __future__ import annotations

import threading
import time

from ..infrastructure import (
    RunnerTaskNotFoundError,
    preview_publication,
    publish_local_outputs,
    runner_poll_task,
    runner_submit_task,
)

from ..config import CACHE_ROOT
from ..errors import PublishingRequestError, PublishingTaskNotFoundError
from .responses import preview_summary, task_summary

_publication_lock = threading.Lock()


from .common import _map_error


def publishing_preview(
    business_line: str,
    publish_date: str,
    account_group: str,
    platforms: list[str],
    content_kind: str | None = None,
    production_id: str | None = None,
    detailed: bool = False,
) -> dict:
    """预检产物及重复项，默认返回精简清单和分阶段耗时；detailed=true 读取完整字段。"""
    try:
        payload = preview_publication(
            business_line,
            publish_date,
            account_group,
            platforms,
            content_kind=content_kind,
            production_id=production_id,
        )
        return payload if detailed else preview_summary(payload)
    except Exception as exc:
        raise _map_error(exc) from exc


def publishing_start_publish(
    business_line: str,
    publish_date: str,
    account_group: str,
    platforms: list[str],
    publish_mode: str | None = None,
    publish_at: str | None = None,
    content_kind: str | None = None,
    publish_at_by_platform: dict[str, str] | None = None,
    production_id: str | None = None,
) -> dict:
    """启动统一发布；财经省略时间时按北京时间14点和18点各一篇，单篇只排18点。"""
    try:
        date_text = str(publish_date or "").strip()
        if not date_text:
            raise PublishingRequestError("publish_date 不能为空；必须先向用户确认要发布哪一天的产物")
        run_id = f"run-{date_text.replace('-', '')}"
        task_run_id = f"{run_id}-{business_line}"

        def _work(progress=None) -> dict:
            if progress:
                progress("等待发布队列；当前发布任务结束后继续")
            with _publication_lock:
                return publish_local_outputs(
                    business_line,
                    date_text,
                    account_group,
                    platforms,
                    publish_mode,
                    publish_at,
                    content_kind=content_kind,
                    production_id=production_id,
                    publish_at_by_platform=publish_at_by_platform,
                    progress=progress,
                )

        started = runner_submit_task(
            cache_dir=CACHE_ROOT / run_id / business_line,
            run_id=task_run_id,
            step="publish",
            fn=_work,
        )
        return {**started, "run_id": run_id, "poll_tool": "publishing_poll_task"}
    except Exception as exc:
        raise _map_error(exc) from exc


def publishing_poll_task(task_path: str, after_revision: str | None = None, detailed: bool = False,
                         wait_seconds: int = 0) -> dict:
    """回传 revision 并设置 wait_seconds=25，最多等待25秒的状态变化；完整明细用 detailed=true。"""
    try:
        deadline = time.monotonic() + min(25, max(0, wait_seconds))
        while True:
            payload = runner_poll_task(task_path=task_path)
            if detailed or (payload.get("result") or {}).get("all_accounts_ready") is not None or str(payload.get("step") or "").startswith("account-check"):
                return payload
            summary = task_summary(payload, after_revision)
            if summary["changed"] or summary["done"] or time.monotonic() >= deadline:
                return summary
            time.sleep(min(1, max(0, deadline - time.monotonic())))
    except RunnerTaskNotFoundError as exc:
        raise PublishingTaskNotFoundError(str(exc), {"task_path": task_path}) from exc
