"""统一视频发布 MCP：`python -m core.mcp.publishing`。"""

from __future__ import annotations

import warnings

warnings.filterwarnings("ignore", message=r"Field 'lifespan' has an incomplete definition.*")

from mcp.server.fastmcp import FastMCP

from core.mcp._task_runner import TaskNotFoundError as RunnerTaskNotFoundError
from core.mcp._task_runner import poll_task as runner_poll_task
from core.mcp._task_runner import submit_task as runner_submit_task
from core.tools.cloudflare_data import CloudflareDataError
from core.tools.publish_media import (
    PublishMediaError,
    list_account_groups,
    preview_publication,
    publish_local_outputs,
)

from ._constants import CACHE_ROOT
from ._errors import PublishingError, PublishingRequestError, PublishingTaskNotFoundError


def _map_error(exc: Exception) -> PublishingError:
    if isinstance(exc, PublishingError):
        return exc
    if isinstance(exc, PublishMediaError):
        return PublishingRequestError(str(exc), {"tool_code": exc.code, **exc.details})
    if isinstance(exc, CloudflareDataError):
        return PublishingRequestError(exc.message, exc.details)
    raise exc


mcp = FastMCP(
    "media-factory-publishing",
    instructions=(
        "统一视频发布 MCP。发布前必须明确业务线、产物计划发布日期、账号组、平台和发布方式。"
        "用户没有说清发布日期时必须先追问，禁止推断；立即发布必须明确传 immediate + now，"
        "预约发布必须传 scheduled + 带时区的未来 ISO 8601 时间。"
        "只允许读取 production_outputs 中已经落库且本地文件存在的 local_mcp 成片；"
        "发布前必须查 publication_records 去重，成功或预约成功后逐条写回数据库。"
        "耗时发布必须调用 publishing_start_publish，再用 publishing_poll_task 轮询。"
    ),
)


@mcp.tool()
def publishing_list_account_groups(business_line: str | None = None) -> dict:
    """列出数据库账号组，并尽量附带 MatrixMedia 当前可见的本机账号。"""
    try:
        return list_account_groups(business_line)
    except Exception as exc:
        raise _map_error(exc) from exc


@mcp.tool()
def publishing_preview(
    business_line: str,
    publish_date: str,
    account_group: str,
    platforms: list[str],
    content_kind: str | None = None,
) -> dict:
    """只读预检指定日期的本地产物、账号路由和数据库重复记录，不执行发布。"""
    try:
        return preview_publication(
            business_line,
            publish_date,
            account_group,
            platforms,
            content_kind=content_kind,
        )
    except Exception as exc:
        raise _map_error(exc) from exc


@mcp.tool()
def publishing_start_publish(
    business_line: str,
    publish_date: str,
    account_group: str,
    platforms: list[str],
    publish_mode: str,
    publish_at: str,
    publish_confirmed: bool,
    content_kind: str | None = None,
) -> dict:
    """启动统一发布；立即发布用 publish_at=now，预约发布使用带时区的未来时间。"""
    try:
        if publish_confirmed is not True:
            raise PublishingRequestError("发布属于外部写操作，publish_confirmed 必须为 true")
        date_text = str(publish_date or "").strip()
        if not date_text:
            raise PublishingRequestError("publish_date 不能为空；必须先向用户确认要发布哪一天的产物")
        run_id = f"run-{date_text.replace('-', '')}"

        def _work(progress=None) -> dict:
            return publish_local_outputs(
                business_line,
                date_text,
                account_group,
                platforms,
                publish_mode,
                publish_at,
                content_kind=content_kind,
                progress=progress,
            )

        started = runner_submit_task(
            cache_dir=CACHE_ROOT / run_id,
            run_id=run_id,
            step="publish",
            fn=_work,
        )
        return {**started, "poll_tool": "publishing_poll_task"}
    except Exception as exc:
        raise _map_error(exc) from exc


@mcp.tool()
def publishing_poll_task(task_path: str) -> dict:
    """轮询发布任务；done=true 后检查 status、result 或 error。"""
    try:
        return runner_poll_task(task_path=task_path)
    except RunnerTaskNotFoundError as exc:
        raise PublishingTaskNotFoundError(str(exc), {"task_path": task_path}) from exc


if __name__ == "__main__":
    mcp.run(transport="stdio")
