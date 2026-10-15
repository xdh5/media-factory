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
from download_video import DownloadError

from ._constants import OUTPUT_ROOT, SERVER_INSTRUCTIONS
from ._errors import AnimeError, TaskNotFoundError, WorkflowStepError
from .services.compile import compile_videos, normalize_share_texts
from .services.discover import discover_series, inspect_works, compile_selection, load_discovery
from .services.youtube import load_manifest, transcribe_intros, publish_youtube, prepare_youtube_thumbnails, save_youtube_thumbnails

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
def anime_start_discover(profile_url: str, series_name: str, limit: int = 300) -> dict:
    """复用 media-collector 扫描抖音主页。轮询后由宿主根据标题描述、集数和发布时间找剧；不明确再取证。"""
    if not profile_url.strip() or not series_name.strip():
        raise WorkflowStepError("必须提供作者主页和目标作品名称")
    if isinstance(limit, bool) or not 1 <= limit <= 1000:
        raise WorkflowStepError("扫描数量必须为 1 到 1000")
    run_id = f"run-{time.time_ns()}"
    directory = OUTPUT_ROOT / run_id
    return {**runner_submit_task(cache_dir=directory, run_id=run_id, step="discover",
            fn=lambda progress: discover_series(profile_url, series_name, limit, directory, progress)),
            "poll_tool": "anime_poll_task"}


@mcp.tool()
def anime_start_inspect(discovery_path: str, work_ids: list[str],
                        window_starts: list[float] | None = None, cover_reason: str = "") -> dict:
    """按需转写指定作品的 45 秒片段，默认从 5 秒开始跳过短片头。封面为最后兜底，必须先完成片段取证并说明原因。转写复用 Groq，封面复用千问视觉，会产生相应服务用量。"""
    directory, _ = load_discovery(discovery_path)
    task_id = f"inspect-{time.time_ns()}"
    return {**runner_submit_task(cache_dir=directory / task_id, run_id=task_id, step="inspect",
            fn=lambda progress: inspect_works(discovery_path, work_ids,
                [5.0] if window_starts is None else window_starts, cover_reason, progress)),
            "poll_tool": "anime_poll_task"}


@mcp.tool()
def anime_start_compile_series(discovery_path: str, work_ids: list[str], selection_reason: str) -> dict:
    """按宿主判断的顺序下载选定作品。必须排除合集与分集的重复覆盖，并在原因中说明排序、覆盖及缺集情况。完整合集只选一条，直接保留原文件；多个来源按既有三小时规则拼接。"""
    directory, _ = load_discovery(discovery_path)
    task_id = f"compile-series-{time.time_ns()}"
    return {**runner_submit_task(cache_dir=directory / task_id, run_id=task_id, step="compile-series",
            fn=lambda progress: compile_selection(discovery_path, work_ids, selection_reason, progress)),
            "poll_tool": "anime_poll_task"}


@mcp.tool()
def anime_start_transcribe_intro(manifest_path: str) -> dict:
    """抽取每段成片前60秒并复用 Groq 转写，供宿主撰写 YouTube 文案。"""
    directory, _ = load_manifest(manifest_path)
    return {**runner_submit_task(cache_dir=directory, run_id=str(directory), step="youtube-intro",
            fn=lambda progress: transcribe_intros(manifest_path, progress)), "poll_tool": "anime_poll_task"}


@mcp.tool()
def anime_prepare_youtube_thumbnails(manifest_path: str, titles: list[str]) -> dict:
    """只抽一帧成片作为画风参考，返回宿主生图任务。宿主一次生成封面，标题和画面一起出图，禁止先出图再叠字。"""
    try:
        return prepare_youtube_thumbnails(manifest_path, titles)
    except Exception as exc:
        raise _map_error(exc) from exc


@mcp.tool()
def anime_save_youtube_thumbnails(context_path: str, images: list[dict]) -> dict:
    """保存宿主生成的 YouTube 封面。images 每项包含 image_id 和 image_path；已缓存的段可以不重复提交。"""
    try:
        return save_youtube_thumbnails(context_path, images)
    except Exception as exc:
        raise _map_error(exc) from exc


@mcp.tool()
def anime_start_publish_youtube(manifest_path: str, titles: list[str], descriptions: list[str], tags: list[str], account_group: str) -> dict:
    """必须获得用户发布授权后使用。发布各段到指定动漫账号组的 YouTube，并上传宿主已生成的封面。未生成封面时拒绝发布。"""
    directory, _ = load_manifest(manifest_path)
    return {**runner_submit_task(cache_dir=directory, run_id=str(directory), step="youtube-publish",
            fn=lambda progress: publish_youtube(manifest_path, titles, descriptions, tags, account_group, progress)),
            "poll_tool": "anime_poll_task"}


@mcp.tool()
def anime_poll_task(task_path: str) -> dict:
    """轮询动漫视频拼接任务。done=true 且 status=succeeded 时，result.parts 是各段成片和原文案。"""
    try:
        return runner_poll_task(task_path=task_path)
    except RunnerTaskNotFoundError as exc:
        raise TaskNotFoundError(str(exc)) from exc


if __name__ == "__main__":
    mcp.run(transport="stdio")
