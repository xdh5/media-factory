"""统一视频发布工作流。"""

from __future__ import annotations

import threading

from ..infrastructure import (
    MediaRecordsError,
    PublishMediaError,
    RunnerTaskNotFoundError,
    list_account_groups,
    publisher_login_status,
    preview_publication,
    publish_local_outputs,
    runner_poll_task,
    runner_submit_task,
    start_publisher_login,
)

from ..config import CACHE_ROOT
from ..errors import PublishingError, PublishingRequestError, PublishingTaskNotFoundError

_publication_lock = threading.Lock()


def _map_error(exc: Exception) -> PublishingError:
    if isinstance(exc, PublishingError):
        return exc
    if isinstance(exc, PublishMediaError):
        return PublishingRequestError(str(exc), {"tool_code": exc.code, **exc.details})
    if isinstance(exc, MediaRecordsError):
        return PublishingRequestError(exc.message, exc.details)
    raise exc


def publishing_list_account_groups(business_line: str | None = None) -> dict:
    """列出数据库账号组，并尽量附带 media-publisher 当前可见的本机账号。"""
    try:
        return list_account_groups(business_line)
    except Exception as exc:
        raise _map_error(exc) from exc


def publishing_preview(
    business_line: str,
    publish_date: str,
    account_group: str,
    platforms: list[str],
    content_kind: str | None = None,
    production_id: str | None = None,
) -> dict:
    """只读预检指定日期的本地产物、账号路由和数据库重复记录，不执行发布。"""
    try:
        return preview_publication(
            business_line,
            publish_date,
            account_group,
            platforms,
            content_kind=content_kind,
            production_id=production_id,
        )
    except Exception as exc:
        raise _map_error(exc) from exc


def publishing_start_login(
    business_line: str,
    account_group: str,
    platform: str,
    timeout_seconds: int = 900,
    force: bool = True,
) -> dict:
    """为抖音、快手、头条或视频号启动 media-publisher 扫码登录，并返回二维码图片路径。"""
    try:
        return start_publisher_login(
            business_line,
            account_group,
            platform,
            timeout_seconds=timeout_seconds,
            force=force,
        )
    except Exception as exc:
        raise _map_error(exc) from exc


def publishing_login_status(login_id: str) -> dict:
    """轮询扫码结果；waiting_scan 时继续向用户展示 qr_path，success 后重新发布。"""
    try:
        return publisher_login_status(login_id)
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


def publishing_poll_task(task_path: str) -> dict:
    """轮询发布任务；done=true 后检查 status、result 或 error。"""
    try:
        return runner_poll_task(task_path=task_path)
    except RunnerTaskNotFoundError as exc:
        raise PublishingTaskNotFoundError(str(exc), {"task_path": task_path}) from exc
