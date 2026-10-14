"""动漫视频拼接 MCP：`python -m core.mcp.anime`。"""

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
from core.tools.download import DownloadError

from ._constants import OUTPUT_ROOT, SERVER_INSTRUCTIONS
from ._errors import AnimeError, TaskNotFoundError, WorkflowStepError
from .services.compile import compile_videos, normalize_share_texts

mcp = FastMCP("media-factory-anime", instructions=SERVER_INSTRUCTIONS)


def _map_error(exc: Exception) -> Exception:
    if isinstance(exc, AnimeError):
        return WorkflowStepError(exc.message, exc.details)
    if isinstance(exc, DownloadError):
        return WorkflowStepError(exc.message, exc.details)
    return exc


@mcp.tool()
def anime_start_compile(share_texts: list[str]) -> dict:
    """按给定顺序下载视频并拼接成每段最长 3 小时的本地成片。标题、描述、话题照搬解析结果。"""
    try:
        texts = normalize_share_texts(share_texts)
        run_id = f"run-{time.time_ns()}"
        cache_dir = OUTPUT_ROOT / run_id

        def _work(progress) -> dict:
            return compile_videos(texts, cache_dir, progress=progress)

        started = runner_submit_task(
            cache_dir=cache_dir,
            run_id=run_id,
            step="compile",
            fn=_work,
        )
        return {
            **started,
            "poll_tool": "anime_poll_task",
            "output_dir": str(cache_dir),
            "link_count": len(texts),
        }
    except Exception as exc:
        raise _map_error(exc) from exc


@mcp.tool()
def anime_poll_task(task_path: str) -> dict:
    """轮询动漫视频拼接任务。done=true 且 status=succeeded 时，result.parts 是各段成片和原文案。"""
    try:
        return runner_poll_task(task_path=task_path)
    except RunnerTaskNotFoundError as exc:
        raise TaskNotFoundError(str(exc)) from exc


if __name__ == "__main__":
    mcp.run(transport="stdio")
