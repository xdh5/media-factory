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
from .services.github_execution import prepare_execution, prepare_split_execution, dispatch_execution, read_execution_result

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
    """扫描并保留主页完整候选。宿主 LLM 需识别人物名别称、改名及误标集号；报告缺集前回查完整列表，不能只按原剧名筛选。不明确再取短片段。"""
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
    """按需转写指定作品的 45 秒片段，默认从 5 秒开始跳过短片头。封面为最后兜底，必须先完成片段取证并说明原因。转写复用 Groq；封面返回图片地址和本地路径，由宿主 Agent 识别。"""
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
def anime_start_prepare_execution(discovery_path: str, work_ids: list[str], selection_reason: str) -> dict:
    """仅接受已确认完结且无缺集的作品。冻结选片顺序，只远程截取第一来源前60秒并转写，返回文案和分段封面所需预览。"""
    directory, _ = load_discovery(discovery_path)
    task_id = f"prepare-execution-{time.time_ns()}"
    return {**runner_submit_task(cache_dir=directory / task_id, run_id=task_id, step="prepare-execution",
            fn=lambda progress: prepare_execution(discovery_path, work_ids, selection_reason, progress)),
            "poll_tool": "anime_poll_task"}


@mcp.tool()
def anime_start_prepare_split_execution(share_texts: list[str], series_name: str, selection_reason: str) -> dict:
    """用户直接给出长视频链接时使用。只远程读取第一来源开头60秒并转写，不下载整部视频；冻结来源后由 Action 下载并按三小时拆分。series_name 用作播放列表名，selection_reason 必须写明已完结。"""
    run_id = f"split-{time.time_ns()}"
    directory = OUTPUT_ROOT / run_id
    return {**runner_submit_task(cache_dir=directory, run_id=run_id, step="prepare-split-execution",
            fn=lambda progress: prepare_split_execution(share_texts, series_name, selection_reason, progress)),
            "poll_tool": "anime_poll_task", "output_dir": str(directory)}


@mcp.tool()
def anime_get_production_config(account_group: str = "") -> dict:
    """只读取得动漫 Action 流程和默认账号组。未指定时自动读取部署配置或唯一启用的数据库动漫 YouTube 组，不要求用户重复提供。"""
    from .services.accounts import production_config
    try:
        return production_config(account_group)
    except Exception as exc:
        raise _map_error(exc) from exc


@mcp.tool()
def anime_dispatch_github_execution(manifest_path: str, titles: list[str], descriptions: list[str],
                                    tags: list[str], account_group: str = "") -> dict:
    """获得用户发布授权后使用。上传执行包和全部分段封面并启动 Action；各段标题标集数并加入作品同名播放列表。长视频拆分清单按时间线切分后同样适用。"""
    try:
        return dispatch_execution(manifest_path, titles, descriptions, tags, account_group)
    except Exception as exc:
        raise _map_error(exc) from exc


@mcp.tool()
def anime_get_github_execution_result(execution_id: str) -> dict:
    """按执行 ID 读取 Action 进度或最终发布结果；无需宿主持续在线轮询。"""
    try:
        return read_execution_result(execution_id)
    except Exception as exc:
        raise _map_error(exc) from exc


@mcp.tool()
def anime_start_transcribe_intro(manifest_path: str) -> dict:
    """抽取第一段成片前60秒并复用 Groq 转写，供宿主撰写 YouTube 文案。"""
    directory, _ = load_manifest(manifest_path)
    return {**runner_submit_task(cache_dir=directory, run_id=str(directory), step="youtube-intro",
            fn=lambda progress: transcribe_intros(manifest_path, progress)), "poll_tool": "anime_poll_task"}


@mcp.tool()
def anime_prepare_youtube_thumbnails(manifest_path: str, titles: list[str]) -> dict:
    """titles 只传一个共用标题；按预计分段数返回独立封面任务，每张标题自动标明第几集。只抽一帧作为共用画风参考。"""
    try:
        return prepare_youtube_thumbnails(manifest_path, titles)
    except Exception as exc:
        raise _map_error(exc) from exc


@mcp.tool()
def anime_save_youtube_thumbnails(context_path: str, images: list[dict]) -> dict:
    """保存宿主生成的分段 YouTube 封面。images 每项包含 image_id 和 image_path；已缓存的封面可以不重复提交。"""
    try:
        return save_youtube_thumbnails(context_path, images)
    except Exception as exc:
        raise _map_error(exc) from exc


@mcp.tool()
def anime_start_publish_youtube(manifest_path: str, titles: list[str], descriptions: list[str],
                                tags: list[str], account_group: str = "",
                                playlist_title: str = "") -> dict:
    """必须获得用户发布授权后使用。多段标题自动标明集数并使用各自封面；playlist_title 非空时创建或复用同名播放列表。"""
    directory, _ = load_manifest(manifest_path)
    return {**runner_submit_task(cache_dir=directory, run_id=str(directory), step="youtube-publish",
            fn=lambda progress: publish_youtube(
                manifest_path, titles, descriptions, tags, account_group, progress,
                playlist_title=playlist_title)),
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
