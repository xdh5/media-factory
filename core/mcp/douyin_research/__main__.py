"""抖音研究 MCP：`python -m core.mcp.douyin_research`。"""

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
from core.tools.douyin_research import (
    DouyinResearchError,
    commit_candidates,
    review_transcripts,
    search_candidates,
)

from ._constants import CACHE_ROOT
from ._errors import TaskNotFoundError, WorkflowStepError


def _map_error(exc: Exception) -> Exception:
    if isinstance(exc, DouyinResearchError):
        return WorkflowStepError(exc.message, exc.details)
    return exc


mcp = FastMCP(
    "media-factory-douyin-research",
    instructions=(
        "抖音关键词研究 MCP。搜索时先用 Cloudflare D1 的作品 ID 去重，再通过 MediaCrawler 按搜索顺序下载前五个新视频，"
        "并调用项目 transcribe 工具转写。宿主 Agent 必须只修正明显错别字、补充标点，不得改写原意；"
        "调用 douyin_research_review_transcripts 保存全部修订文本后，向用户只展示编号和修订后的文字，禁止展示作者、时间、文案或链接。"
        "只有用户明确确认编号后，才能调用 douyin_research_commit 写入 D1。搜索为耗时任务，必须 start + poll_task。"
    ),
)


@mcp.tool()
def douyin_research_start_search(keyword: str, limit: int = 5) -> dict:
    """启动抖音关键词搜索、去重、视频下载和语音转写。"""
    try:
        run_id = f"run-{time.time_ns()}"
        cache_dir = CACHE_ROOT / run_id

        def _work() -> dict:
            return search_candidates(keyword, cache_dir, limit=limit)

        started = runner_submit_task(
            cache_dir=cache_dir,
            run_id=run_id,
            step="search_and_transcribe",
            fn=_work,
        )
        return {**started, "poll_tool": "douyin_research_poll_task"}
    except Exception as exc:
        raise _map_error(exc) from exc


@mcp.tool()
def douyin_research_poll_task(task_path: str) -> dict:
    """轮询搜索和转写任务。"""
    try:
        return runner_poll_task(task_path=task_path)
    except RunnerTaskNotFoundError as exc:
        raise TaskNotFoundError(str(exc)) from exc


@mcp.tool()
def douyin_research_review_transcripts(context_path: str, reviews: list[dict]) -> dict:
    """保存宿主 Agent 对全部候选转写的错别字修正和标点整理。"""
    try:
        return review_transcripts(context_path, reviews)
    except Exception as exc:
        raise _map_error(exc) from exc


@mcp.tool()
def douyin_research_commit(
    context_path: str,
    candidate_numbers: list[int],
    confirmed: bool,
) -> dict:
    """用户确认后，把指定作品元数据和最终转写写入 Cloudflare D1。"""
    try:
        return commit_candidates(
            context_path,
            candidate_numbers,
            confirmed=confirmed,
        )
    except Exception as exc:
        raise _map_error(exc) from exc


if __name__ == "__main__":
    mcp.run(transport="stdio")
