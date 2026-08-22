"""财经 MCP：`python -m core.mcp.finance`。"""

from __future__ import annotations

import warnings
from pathlib import Path

warnings.filterwarnings(
    "ignore",
    message=r"Field 'lifespan' has an incomplete definition.*",
)

from mcp.server.fastmcp import FastMCP

from core.tools.clear_cache import ConfirmationRequiredError as ClearCacheConfirmationRequiredError
from core.tools.clear_cache import clear_run
from core.tools.generate_image import (
    ImageGenerationError,
    save_agent_image_tasks,
    submit_agent_image_tasks,
)
from core.tools.topic_dedup import TopicDedupError, get_topic

from core.mcp._task_runner import TaskNotFoundError as RunnerTaskNotFoundError
from core.mcp._task_runner import poll_task as runner_poll_task
from core.mcp._task_runner import submit_task as runner_submit_task

from ._constants import MCP_ID, TOPIC_DEDUPLICATION_DAYS
from ._errors import ConfirmationRequiredError, FinanceError, TaskNotFoundError, WorkflowStepError
from .tools import (
    build_metadata_prompt,
    finish_finance_video,
    prepare_shot_images,
    prepare_storyboard,
    save_draft,
)
from .tools.save_draft import load_draft


def _map_error(exc: Exception) -> FinanceError:
    if isinstance(exc, FinanceError):
        return exc
    if isinstance(exc, ImageGenerationError):
        return WorkflowStepError(exc.message, exc.details)
    if isinstance(exc, TopicDedupError):
        return WorkflowStepError(str(exc), exc.details)
    if isinstance(exc, ClearCacheConfirmationRequiredError):
        return ConfirmationRequiredError(str(exc))
    raise exc


mcp = FastMCP(
    "media-factory-finance",
    instructions=(
        "财经短视频编排 MCP。业务 Prompt、生图方案、TTS、BGM、片头等以财经 Skill 为准，"
        "Agent 必须按 Skill 传参。"
        "稿件生成后直接制作视频；成品完成后展示成片并等待确认再发布。"
        "耗时步骤（TTS、成片合成）必须用 start + poll_task 轮询，禁止同步调用以免 MCP 超时。"
        "禁止绕过 MCP 运行本地脚本。"
    ),
)


@mcp.tool()
def finance_get_topics() -> dict:
    """返回最近 30 天已占用话题。"""
    try:
        recent = get_topic(MCP_ID, TOPIC_DEDUPLICATION_DAYS)
        return {
            "workflow": MCP_ID,
            "deduplication_days": TOPIC_DEDUPLICATION_DAYS,
            "recent_topics": [item["topic"] for item in recent],
        }
    except Exception as exc:
        raise _map_error(exc) from exc


@mcp.tool()
def finance_get_metadata_prompt() -> dict:
    """返回标题标签生成 Prompt；Agent 按原样生成 metadata 行。"""
    try:
        return build_metadata_prompt()
    except Exception as exc:
        raise _map_error(exc) from exc


@mcp.tool()
def finance_save_draft(
    topic: str,
    article: str,
    title: str,
    short_title: str,
    hashtags: list[str],
    cover_lines: list[str],
    draft_path: str | None = None,
) -> dict:
    """保存完整稿件并直接返回制作所需数据。"""
    try:
        return save_draft(
            topic,
            article,
            title,
            short_title,
            hashtags,
            cover_lines,
            draft_path,
        )
    except Exception as exc:
        raise _map_error(exc) from exc


@mcp.tool()
def finance_prepare_storyboard(
    draft_path: str,
    tts_config: dict,
) -> dict:
    """生成 TTS 与分镜上下文（同步，易超时）。优先使用 finance_start_storyboard + poll_task。"""
    try:
        return prepare_storyboard(draft_path, tts_config=tts_config)
    except Exception as exc:
        raise _map_error(exc) from exc


@mcp.tool()
def finance_start_storyboard(
    draft_path: str,
    tts_config: dict,
) -> dict:
    """启动 TTS 与分镜上下文生成；立即返回 task_path，用 finance_poll_task 轮询至 done=true。"""
    try:
        _, draft = load_draft(draft_path, "财经稿件")
        cache_dir = Path(str(draft["cache_dir"]))
        run_id = str(draft["run_id"])

        def _work() -> dict:
            return prepare_storyboard(draft_path, tts_config=tts_config)

        started = runner_submit_task(
            cache_dir=cache_dir,
            run_id=run_id,
            step="prepare_storyboard",
            fn=_work,
        )
        return {**started, "poll_tool": "finance_poll_task"}
    except Exception as exc:
        raise _map_error(exc) from exc


@mcp.tool()
def finance_poll_task(task_path: str) -> dict:
    """轮询后台任务。status=succeeded 时读 result；failed 时读 error 并停止制作。"""
    try:
        return runner_poll_task(task_path=task_path)
    except RunnerTaskNotFoundError as exc:
        raise TaskNotFoundError(str(exc), {"task_path": task_path}) from exc


@mcp.tool()
def finance_prepare_images(
    draft_path: str,
    storyboard_text: str,
    image_config: dict,
) -> dict:
    """按 Skill 的 image_config 准备镜头图任务；本地图库时返回 catalog 与 selection_tasks，由 Agent 选图后 submit。"""
    try:
        return prepare_shot_images(
            draft_path,
            storyboard_text,
            image_config=image_config,
        )
    except Exception as exc:
        raise _map_error(exc) from exc


@mcp.tool()
def finance_save_images(context_path: str, images: list[dict]) -> dict:
    """把已生成的图片立刻写入本次生产缓存。"""
    try:
        return save_agent_image_tasks(context_path, images)
    except ImageGenerationError as exc:
        raise WorkflowStepError(exc.message, exc.details) from exc


@mcp.tool()
def finance_submit_images(
    context_path: str,
    images: list[dict],
    failures: list[dict] | None = None,
) -> dict:
    """接收选图/生图结果并写出清单。"""
    try:
        return submit_agent_image_tasks(context_path, images)
    except ImageGenerationError as exc:
        raise WorkflowStepError(exc.message, exc.details) from exc


@mcp.tool()
def finance_finish_video(
    draft_path: str,
    image_manifest_path: str,
    production_config: dict,
    storyboard_text: str | None = None,
    force_shot_ids: list[str] | None = None,
) -> dict:
    """合成成片（同步，易超时）。优先使用 finance_start_finish_video + poll_task。"""
    try:
        return finish_finance_video(
            draft_path,
            image_manifest_path=image_manifest_path,
            production_config=production_config,
            storyboard_text=storyboard_text,
            force_shot_ids=force_shot_ids,
        )
    except Exception as exc:
        raise _map_error(exc) from exc


@mcp.tool()
def finance_start_finish_video(
    draft_path: str,
    image_manifest_path: str,
    production_config: dict,
    storyboard_text: str | None = None,
    force_shot_ids: list[str] | None = None,
) -> dict:
    """启动成片合成；立即返回 task_path，用 finance_poll_task 轮询至 done=true。"""
    try:
        _, draft = load_draft(draft_path, "财经稿件")
        cache_dir = Path(str(draft["cache_dir"]))
        run_id = str(draft["run_id"])

        def _work(progress=None) -> dict:
            return finish_finance_video(
                draft_path,
                image_manifest_path=image_manifest_path,
                production_config=production_config,
                storyboard_text=storyboard_text,
                force_shot_ids=force_shot_ids,
                progress=progress,
            )

        started = runner_submit_task(
            cache_dir=cache_dir,
            run_id=run_id,
            step="finish_video",
            fn=_work,
        )
        return {**started, "poll_tool": "finance_poll_task"}
    except Exception as exc:
        raise _map_error(exc) from exc


@mcp.tool()
def finance_clear_run(run_id: str, confirmed: bool) -> dict:
    """用户确认后删除本次生产目录（cache 和成品），保留话题库记录。"""
    try:
        return clear_run(MCP_ID, run_id, confirmed=confirmed)
    except ClearCacheConfirmationRequiredError as exc:
        raise ConfirmationRequiredError(str(exc)) from exc


if __name__ == "__main__":
    mcp.run(transport="stdio")
