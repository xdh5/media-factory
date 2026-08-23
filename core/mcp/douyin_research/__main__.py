"""抖音链接入库 MCP：`python -m core.mcp.douyin_research`。"""

from __future__ import annotations

import time
import warnings

warnings.filterwarnings(
    "ignore",
    message=r"Field 'lifespan' has an incomplete definition.*",
)

from mcp.server.fastmcp import FastMCP

from core.mcp._task_runner import TaskNotFoundError as RunnerTaskNotFoundError
from core.mcp._task_runner import poll_task as runner_poll_task
from core.mcp._task_runner import submit_task as runner_submit_task
from core.tools.douyin_research import DouyinResearchError, ingest_link

from ._constants import CACHE_ROOT
from ._errors import TaskNotFoundError, WorkflowStepError


def _map_error(exc: Exception) -> Exception:
    if isinstance(exc, DouyinResearchError):
        return WorkflowStepError(exc.message, exc.details)
    return exc


mcp = FastMCP(
    "media-factory-douyin-research",
    instructions=(
        "抖音链接下载、转写和分类入库 MCP。用户只需提供抖音分享链接或分享文字以及中文分类名。"
        "必须调用 douyin_research_start_ingest 启动后台任务，再用返回的 task_path 调用 "
        "douyin_research_poll_task，直到 done=true；不得重复启动同一链接。"
        "流程只编排 core.tools.download、core.tools.transcribe 和 Cloudflare D1 写入，禁止调用 MediaCrawler 或浏览器搜索。"
    ),
)


@mcp.tool()
def douyin_research_start_ingest(
    share_text: str,
    collection_name: str,
) -> dict:
    """启动抖音链接下载、中文转写和分类入库后台任务。"""
    try:
        run_id = f"run-{time.time_ns()}"
        cache_dir = CACHE_ROOT / run_id

        def _work() -> dict:
            return ingest_link(
                share_text,
                cache_dir,
                collection_name=collection_name,
            )

        started = runner_submit_task(
            cache_dir=cache_dir,
            run_id=run_id,
            step="download_transcribe_commit",
            fn=_work,
        )
        return {**started, "poll_tool": "douyin_research_poll_task"}
    except Exception as exc:
        raise _map_error(exc) from exc


@mcp.tool()
def douyin_research_poll_task(task_path: str) -> dict:
    """轮询抖音链接下载、转写和入库任务。"""
    try:
        return runner_poll_task(task_path=task_path)
    except RunnerTaskNotFoundError as exc:
        raise TaskNotFoundError(str(exc)) from exc


if __name__ == "__main__":
    mcp.run(transport="stdio")
