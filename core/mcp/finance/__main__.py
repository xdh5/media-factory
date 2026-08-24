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
from core.tools.cloudflare_data import (
    CloudflareDataError,
    commit_publication_records,
    get_douyin_research_script_stats,
    mark_douyin_research_script_used,
    reserve_douyin_research_script,
)
from core.tools.generate_image import (
    ImageGenerationError,
    save_agent_image_tasks,
    submit_agent_image_tasks,
)
from core.tools.r2_storage import R2StorageError
from core.tools.topic_dedup import TopicDedupError, get_topic

from core.mcp._task_runner import TaskNotFoundError as RunnerTaskNotFoundError
from core.mcp._task_runner import poll_task as runner_poll_task
from core.mcp._task_runner import submit_task as runner_submit_task

from ._constants import (
    MCP_ID,
    SOURCE_COLLECTION_CODE,
    SOURCE_RESERVATION_MINUTES,
    TOPIC_DEDUPLICATION_DAYS,
)
from ._errors import ConfirmationRequiredError, FinanceError, TaskNotFoundError, WorkflowStepError
from .tools import (
    build_metadata_prompt,
    commit_existing_qwen_shot_images,
    finish_finance_video,
    generate_qwen_shot_images,
    prepare_shot_images,
    prepare_storyboard,
    save_draft,
    save_source_usage,
    upload_finance_assets_to_r2,
)
from .tools.save_draft import load_draft


def _map_error(exc: Exception) -> FinanceError:
    if isinstance(exc, FinanceError):
        return exc
    if isinstance(exc, ImageGenerationError):
        return WorkflowStepError(exc.message, exc.details)
    if isinstance(exc, TopicDedupError):
        return WorkflowStepError(str(exc), exc.details)
    if isinstance(exc, R2StorageError):
        return WorkflowStepError(exc.message, exc.details)
    if isinstance(exc, ClearCacheConfirmationRequiredError):
        return ConfirmationRequiredError(str(exc))
    if isinstance(exc, CloudflareDataError):
        details = dict(exc.details)
        remote_code = str(getattr(exc, "remote_code", "")).strip()
        if remote_code:
            details["remote_code"] = remote_code
        return WorkflowStepError(exc.message, details)
    raise exc


mcp = FastMCP(
    "media-factory-finance",
    instructions=(
        "财经短视频编排 MCP。业务 Prompt、生图方案、TTS、BGM、片头等以财经 Skill 为准，"
        "Agent 必须按 Skill 传参。"
        "第一步必须从抖音研究数据库选择未使用的财经稿件，禁止自行从零写正文；"
        "保存稿件成功后必须把数据库来源标记为已使用。"
        "查询稿件余量必须使用只读的 finance_get_source_stats，不得用选稿工具代替统计。"
        "本地交互制作使用用户参考图逐镜头调用千问生图，每张图都必须有独立任务；"
        "GitHub Action 从统一财经生成图库按场景描述选图。"
        "稿件生成后直接制作视频；成品完成后展示成片并等待确认再发布。"
        "耗时步骤（TTS、成片合成）必须用 start + poll_task 轮询，禁止同步调用以免 MCP 超时。"
        "禁止绕过 MCP 运行本地脚本。"
    ),
)


@mcp.tool()
def finance_get_source_stats() -> dict:
    """只读统计财经数据库原稿总数、可用数、占用数和已使用数，不占用稿件。"""
    try:
        return get_douyin_research_script_stats(
            collection_code=SOURCE_COLLECTION_CODE,
            workflow=MCP_ID,
            reservation_minutes=SOURCE_RESERVATION_MINUTES,
        )
    except Exception as exc:
        raise _map_error(exc) from exc


@mcp.tool()
def finance_record_publications(
    publication_id: str,
    run_id: str,
    records: list[dict],
) -> dict:
    """MatrixMedia 发布成功或预约成功后，按最终平台写入财经发布记录。"""
    try:
        normalized = [
            {
                **record,
                "publication_id": publication_id,
                "run_id": run_id,
                "business_line": "finance",
                "connector": "matrixmedia",
            }
            for record in records
        ]
        return commit_publication_records(normalized)
    except Exception as exc:
        raise _map_error(exc) from exc


@mcp.tool()
def finance_get_source_script() -> dict:
    """从抖音研究数据库选择并临时占用一条未使用的财经稿件。"""
    try:
        return reserve_douyin_research_script(
            collection_code=SOURCE_COLLECTION_CODE,
            workflow=MCP_ID,
            reservation_minutes=SOURCE_RESERVATION_MINUTES,
        )
    except Exception as exc:
        raise _map_error(exc) from exc


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
    source_aweme_id: str,
    source_reservation_token: str,
    source_hook: str,
    draft_path: str | None = None,
    cover_highlights: list[str] | None = None,
) -> dict:
    """保存数据库改编稿，随后把来源稿件标记为已使用。"""
    try:
        if draft_path is None:
            clean_topic = str(topic or "").strip()
            recent = get_topic(MCP_ID, TOPIC_DEDUPLICATION_DAYS)
            if clean_topic.casefold() in {
                str(item.get("topic") or "").strip().casefold() for item in recent
            }:
                raise WorkflowStepError(
                    f"财经话题最近 {TOPIC_DEDUPLICATION_DAYS} 天已经发布：{clean_topic}"
                )
        draft = save_draft(
            topic,
            article,
            title,
            short_title,
            hashtags,
            cover_lines,
            source_aweme_id,
            source_reservation_token,
            source_hook,
            draft_path,
            cover_highlights,
        )
        usage = mark_douyin_research_script_used(
            aweme_id=str(draft["source_aweme_id"]),
            workflow=MCP_ID,
            reservation_token=str(draft["source_reservation_token"]),
            run_id=str(draft["run_id"]),
            source_hook=str(draft["source_hook"]),
        )
        return save_source_usage(str(draft["draft_path"]), usage)
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
    """按 Skill 准备镜头图；支持旧图库选图和用户参考图千问生图两种模式。"""
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
def finance_start_generate_images(context_path: str) -> dict:
    """启动全部镜头的千问参考图生图与独立图库入库。"""
    try:
        _, context = load_draft(context_path, "千问生图任务上下文")
        metadata = context.get("metadata")
        if not isinstance(metadata, dict):
            raise WorkflowStepError("千问生图任务上下文缺少 metadata")
        draft_path = str(metadata.get("draft_path") or "")
        _, draft = load_draft(draft_path, "财经稿件")
        cache_dir = Path(str(draft["cache_dir"]))
        run_id = str(draft["run_id"])

        def _work(progress=None) -> dict:
            return generate_qwen_shot_images(context_path, progress=progress)

        started = runner_submit_task(
            cache_dir=cache_dir,
            run_id=run_id,
            step="generate_qwen_images",
            fn=_work,
        )
        return {**started, "poll_tool": "finance_poll_task"}
    except Exception as exc:
        raise _map_error(exc) from exc


@mcp.tool()
def finance_commit_existing_images(context_path: str) -> dict:
    """仅校验现有镜头图片并写入 D1；绝不重新调用千问生图。"""
    try:
        return commit_existing_qwen_shot_images(context_path)
    except Exception as exc:
        raise _map_error(exc) from exc


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
def finance_start_upload_r2(manifest_path: str, run_id: str) -> dict:
    """启动财经成片、封面和发布清单上传 R2。"""
    try:
        cache_dir = Path(manifest_path).resolve().parent

        def _work() -> dict:
            return upload_finance_assets_to_r2(manifest_path)

        started = runner_submit_task(
            cache_dir=cache_dir,
            run_id=run_id,
            step="upload_r2",
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
