"""心灵鸡汤 MCP：`python -m core.mcp.psychology_quiz`。"""

from __future__ import annotations

import os
import warnings
from pathlib import Path

os.environ.setdefault("DASHSCOPE_BUSINESS_LINE", "psychology_quiz")
warnings.filterwarnings("ignore", message=r"Field 'lifespan' has an incomplete definition.*")

from mcp.server.fastmcp import FastMCP

from core.mcp._task_runner import TaskNotFoundError as RunnerTaskNotFoundError
from core.mcp._task_runner import poll_task as runner_poll_task
from core.mcp._task_runner import submit_task as runner_submit_task
from core.tools.clear_cache import ConfirmationRequiredError as ClearCacheConfirmationRequiredError
from core.tools.clear_cache import clear_run
from core.tools.cloudflare_data import (
    CloudflareDataError,
    list_production_outputs,
)
from core.tools.stock_video import StockVideoError
from core.tools.topic_dedup import TopicDedupError, get_topic, update

from ._constants import ARTICLE_PROMPT_PATH, MCP_ID, TOPIC_DEDUPLICATION_DAYS
from ._errors import ConfirmationRequiredError, PsychologyQuizError, TaskNotFoundError, WorkflowStepError
from .tools import (
    finish_psychology_quiz_video,
    load_draft,
    download_selected_videos,
    prepare_video_searches,
    prepare_storyboard,
    save_article_draft,
    validate_article_fields,
)


def _map_error(exc: Exception) -> PsychologyQuizError:
    if isinstance(exc, PsychologyQuizError):
        return exc
    if isinstance(exc, StockVideoError):
        return WorkflowStepError(exc.message, exc.details)
    if isinstance(exc, TopicDedupError):
        return WorkflowStepError(str(exc), exc.details)
    if isinstance(exc, ClearCacheConfirmationRequiredError):
        return ConfirmationRequiredError(str(exc))
    if isinstance(exc, CloudflareDataError):
        details = dict(exc.details)
        remote_code = str(getattr(exc, "remote_code", "")).strip()
        if remote_code:
            details["remote_code"] = remote_code
        return WorkflowStepError(exc.message, details)
    if isinstance(exc, ValueError):
        return WorkflowStepError(str(exc))
    raise exc


mcp = FastMCP(
    "media-factory-psychology-quiz",
    instructions=(
        "心灵鸡汤短视频独立编排 MCP。交互式生产前必须明确北京时间计划发布日期 publish_date。"
        "内容由用户提供文章，宿主 Agent 按成稿规则压缩到 1000 字左右："
        "保留原文结构、黄金钩子和原话，只改细枝末节；不足 1000 字直接用原文；品牌一律改为财富研习岛。"
        "交互式生产由宿主 Agent 提炼片头场景、分镜、生成一张写实片头图并选择正文视频；"
        "只有片头允许生图；正文镜头只允许通过公共 stock_video 工具从 Pexels、Pixabay、Coverr 搜索和下载。"
        "字幕样式和字幕位置由本 MCP 的参数独立控制，不得反向调用 Finance MCP 内部实现。"
        "耗时步骤必须使用 start + psychology_quiz_poll_task 轮询。"
    ),
)


@mcp.tool()
def psychology_quiz_get_prompt() -> dict:
    """返回心灵鸡汤文章成稿规则与最近30天已用话题。"""
    try:
        recent = get_topic(MCP_ID, TOPIC_DEDUPLICATION_DAYS)
        return {
            "article_prompt": ARTICLE_PROMPT_PATH.read_text(encoding="utf-8"),
            "deduplication_days": TOPIC_DEDUPLICATION_DAYS,
            "recent_topics": [item["topic"] for item in recent],
            "generator": "host_agent",
        }
    except Exception as exc:
        raise _map_error(exc) from exc


@mcp.tool()
def psychology_quiz_get_production_outputs(publish_date: str) -> dict:
    """按北京时间计划发布日期查询心灵鸡汤成片。"""
    try:
        return {
            "publish_date": publish_date,
            "business_line": MCP_ID,
            "records": list_production_outputs(publish_date=publish_date, business_line=MCP_ID),
        }
    except Exception as exc:
        raise _map_error(exc) from exc


@mcp.tool()
def psychology_quiz_save_draft(
    topic: str,
    article: str,
    intro_scene: str,
    title: str,
    short_title: str,
    hashtags: list[str],
    cover_lines: list[str],
    cover_highlights: list[str],
    publish_date: str,
    draft_path: str | None = None,
) -> dict:
    """校验并保存心灵鸡汤文章稿件，使用共用话题库做30天原子去重。"""
    try:
        validate_article_fields(
            article=article,
            intro_scene=intro_scene,
            title=title,
            short_title=short_title,
            hashtags=hashtags,
            cover_lines=cover_lines,
            cover_highlights=cover_highlights,
        )
        if draft_path is None:
            topic_record = update(MCP_ID, topic, TOPIC_DEDUPLICATION_DAYS)
        else:
            _, existing = load_draft(draft_path, "待修改心灵鸡汤稿件")
            topic_record = {"id": int(existing["topic_record_id"]), "topic": str(existing["topic"])}
        return save_article_draft(
            topic=topic,
            article=article,
            intro_scene=intro_scene,
            title=title,
            short_title=short_title,
            hashtags=hashtags,
            cover_lines=cover_lines,
            cover_highlights=cover_highlights,
            publish_date=publish_date,
            topic_record=topic_record,
            draft_path=draft_path,
        )
    except Exception as exc:
        raise _map_error(exc) from exc


@mcp.tool()
def psychology_quiz_start_storyboard(draft_path: str, tts_config: dict) -> dict:
    """启动 TTS 和分镜上下文生成。"""
    try:
        _, draft = load_draft(draft_path, "心灵鸡汤稿件")

        def _work() -> dict:
            return prepare_storyboard(draft_path, tts_config=tts_config)

        started = runner_submit_task(
            cache_dir=Path(str(draft["cache_dir"])),
            run_id=str(draft["run_id"]),
            step="prepare_storyboard",
            fn=_work,
        )
        return {**started, "poll_tool": "psychology_quiz_poll_task"}
    except Exception as exc:
        raise _map_error(exc) from exc


@mcp.tool()
def psychology_quiz_poll_task(task_path: str) -> dict:
    """轮询心灵鸡汤后台任务。"""
    try:
        return runner_poll_task(task_path=task_path)
    except RunnerTaskNotFoundError as exc:
        raise TaskNotFoundError(str(exc), {"task_path": task_path}) from exc


@mcp.tool()
def psychology_quiz_start_video_search(
    draft_path: str,
    storyboard_text: str,
    video_config: dict,
) -> dict:
    """后台从 Pexels、Pixabay、Coverr 逐镜头搜索视频候选。"""
    try:
        _, draft = load_draft(draft_path, "心灵鸡汤稿件")

        def _work(progress=None) -> dict:
            return prepare_video_searches(
                draft_path,
                storyboard_text,
                video_config=video_config,
                progress=progress,
            )

        started = runner_submit_task(
            cache_dir=Path(str(draft["cache_dir"])),
            run_id=str(draft["run_id"]),
            step="search_stock_videos",
            fn=_work,
        )
        return {**started, "poll_tool": "psychology_quiz_poll_task"}
    except Exception as exc:
        raise _map_error(exc) from exc


@mcp.tool()
def psychology_quiz_start_download_videos(context_path: str, selections: list[dict]) -> dict:
    """后台下载选择的视频并规范化为与配音一致的镜头。"""
    try:
        resolved_context, context = load_draft(context_path, "正版视频搜索上下文")
        metadata = context.get("metadata")
        if not isinstance(metadata, dict):
            raise WorkflowStepError("正版视频搜索上下文缺少 metadata")
        _, draft = load_draft(str(metadata.get("draft_path") or ""), "心灵鸡汤稿件")

        def _work(progress=None) -> dict:
            return download_selected_videos(resolved_context, selections, progress=progress)

        started = runner_submit_task(
            cache_dir=Path(str(draft["cache_dir"])),
            run_id=str(draft["run_id"]),
            step="download_stock_videos",
            fn=_work,
        )
        return {**started, "poll_tool": "psychology_quiz_poll_task"}
    except Exception as exc:
        raise _map_error(exc) from exc


@mcp.tool()
def psychology_quiz_start_finish_video(
    draft_path: str,
    video_manifest_path: str,
    intro_image_path: str,
    production_config: dict,
    storyboard_text: str | None = None,
    force_shot_ids: list[str] | None = None,
    production_source: str = "local_mcp",
) -> dict:
    """启动心灵鸡汤成片合成，字幕样式与位置从 production_config 读取。"""
    try:
        _, draft = load_draft(draft_path, "心灵鸡汤稿件")

        def _work(progress=None) -> dict:
            return finish_psychology_quiz_video(
                draft_path,
                video_manifest_path=video_manifest_path,
                intro_image_path=intro_image_path,
                production_config=production_config,
                storyboard_text=storyboard_text,
                force_shot_ids=force_shot_ids,
                production_source=production_source,
                progress=progress,
            )

        started = runner_submit_task(
            cache_dir=Path(str(draft["cache_dir"])),
            run_id=str(draft["run_id"]),
            step="finish_video",
            fn=_work,
        )
        return {**started, "poll_tool": "psychology_quiz_poll_task"}
    except Exception as exc:
        raise _map_error(exc) from exc


@mcp.tool()
def psychology_quiz_clear_run(run_id: str, confirmed: bool) -> dict:
    """用户确认后清理本次心灵鸡汤缓存与成片。"""
    try:
        return clear_run(MCP_ID, run_id, confirmed=confirmed)
    except ClearCacheConfirmationRequiredError as exc:
        raise ConfirmationRequiredError(str(exc)) from exc


if __name__ == "__main__":
    mcp.run(transport="stdio")
