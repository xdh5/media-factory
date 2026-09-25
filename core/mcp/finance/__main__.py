"""财经 MCP：`python -m core.mcp.finance`。"""

from __future__ import annotations

import os
import warnings
from copy import deepcopy
from pathlib import Path

os.environ.setdefault("DASHSCOPE_BUSINESS_LINE", "finance")

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
    list_production_outputs,
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
    AUTOMATION_DAILY_OUTPUT_COUNT,
    DEFAULT_PRODUCTION_CONFIG,
    MCP_ID,
    SOURCE_COLLECTION_CODE,
    SOURCE_RESERVATION_MINUTES,
    TOPIC_DEDUPLICATION_DAYS,
    normalize_publish_date,
)
from ._errors import ConfirmationRequiredError, FinanceError, TaskNotFoundError, WorkflowStepError
from .tools import (
    build_article_generation_prompt,
    build_article_chunk_generation_prompt,
    build_article_prompt,
    build_metadata_generation_prompt,
    build_source_hook_prompt,
    build_stock_video_selection_prompt,
    build_topic_prompt,
    plan_article_chunks,
    build_metadata_prompt,
    commit_existing_qwen_shot_images,
    download_selected_videos,
    finish_finance_video,
    generate_qwen_shot_images,
    prepare_shot_images,
    prepare_storyboard,
    prepare_video_searches,
    save_draft,
    save_source_usage,
    upload_finance_assets_to_r2,
    validate_article_response,
    validate_article_chunk_response,
    validate_metadata_response,
    validate_source_hook_response,
    validate_stock_video_selection_response,
    validate_topic_response,
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
        "财经短视频编排 MCP。素材方案、TTS、BGM、片头等生产参数以 finance_get_production_config 为唯一标准，"
        "Agent 与 GitHub Runner 都必须先读取并复用。"
        "交互式生产前必须先向用户确认北京时间计划发布日期 publish_date；日期不明确时禁止选稿、创建 run、生产或落库。"
        "第一步必须从抖音研究数据库选择未使用的原稿，禁止自行从零写正文；"
        "正文执行三类必做改动（品牌替换、连载指涉改写、错别字修正）之外允许措辞级改写，保留大结构与信息量并按语义断行；"
        "保存稿件成功后必须把数据库来源标记为已使用。"
        "查询稿件余量必须使用只读的 finance_get_source_stats，不得用选稿工具代替统计。"
        "镜头素材有三类并列策略，默认值由 finance_get_production_config 返回："
        "image_library（存量图库选图）、"
        "qwen_reference（用户参考图 + 千问逐镜头生图）、"
        "stock_video（Pexels/Pixabay/Coverr 正版实拍视频 + 片头写实图）。"
        "稿件生成后直接制作视频；成品完成后展示成片并等待确认再发布。"
        "耗时步骤（TTS、素材、成片合成）必须用 start + poll_task 轮询，禁止同步调用以免 MCP 超时。"
        "禁止绕过 MCP 运行本地脚本。"
    ),
)


@mcp.tool()
def finance_get_production_config() -> dict:
    """返回财经生产唯一标准配置，供 Agent 与 GitHub Runner 共用。"""
    return deepcopy(DEFAULT_PRODUCTION_CONFIG)


@mcp.tool()
def finance_get_automation_plan(publish_date: str) -> dict:
    """按计划发布日期返回 GitHub 财经待生产分片；每天目标数量由 MCP 统一维护。"""
    try:
        normalized_date = normalize_publish_date(publish_date)
        records = list_production_outputs(publish_date=normalized_date, business_line=MCP_ID)
        existing_parts = {
            int(item.get("content_part") or 1)
            for item in records
            if 1 <= int(item.get("content_part") or 1) <= AUTOMATION_DAILY_OUTPUT_COUNT
        }
        pending_parts = [
            part
            for part in range(1, AUTOMATION_DAILY_OUTPUT_COUNT + 1)
            if part not in existing_parts
        ]
        return {
            "publish_date": normalized_date,
            "should_generate": bool(pending_parts),
            "output_count": len(records),
            "desired_output_count": AUTOMATION_DAILY_OUTPUT_COUNT,
            "pending_content_parts": pending_parts,
            "skip_reason": "" if pending_parts else f"该计划发布日期已有 {len(existing_parts)} 条财经成片记录，已达到每日目标",
        }
    except Exception as exc:
        raise _map_error(exc) from exc


@mcp.tool()
def finance_get_source_hook_prompt(source_text: str, feedback: str = "") -> dict:
    try:
        return build_source_hook_prompt(source_text, feedback)
    except Exception as exc:
        raise _map_error(exc) from exc


@mcp.tool()
def finance_validate_source_hook_response(source_text: str, response_text: str) -> dict:
    try:
        return validate_source_hook_response(source_text, response_text)
    except Exception as exc:
        raise _map_error(exc) from exc


@mcp.tool()
def finance_get_article_generation_prompt(article_prompt: str, source_text: str, source_hook: str, feedback: str = "", previous_response: str = "") -> dict:
    try:
        return build_article_generation_prompt(article_prompt, source_text, source_hook, feedback, previous_response)
    except Exception as exc:
        raise _map_error(exc) from exc


@mcp.tool()
def finance_get_article_chunk_plan(source_text: str, source_hook: str) -> dict:
    """按钩子和语义短句拆分财经正文，供 Runner 逐段生成。"""
    try:
        return plan_article_chunks(source_text, source_hook)
    except Exception as exc:
        raise _map_error(exc) from exc


@mcp.tool()
def finance_get_article_chunk_generation_prompt(source_chunk: str, source_hook: str = "", feedback: str = "", previous_response: str = "") -> dict:
    """返回单个财经正文片段的模型 Prompt。"""
    try:
        return build_article_chunk_generation_prompt(source_chunk, source_hook, feedback, previous_response)
    except Exception as exc:
        raise _map_error(exc) from exc


@mcp.tool()
def finance_validate_article_chunk_response(source_chunk: str, source_hook: str = "", response_text: str = "") -> dict:
    """校验单个财经正文片段；失败时只需重试当前片段。"""
    try:
        return validate_article_chunk_response(source_chunk, source_hook, response_text)
    except Exception as exc:
        raise _map_error(exc) from exc


@mcp.tool()
def finance_validate_article_response(source_text: str, source_hook: str, response_text: str) -> dict:
    try:
        return validate_article_response(source_text, source_hook, response_text)
    except Exception as exc:
        raise _map_error(exc) from exc


@mcp.tool()
def finance_get_topic_generation_prompt(article: str, recent_topics: list[str], requested_topic: str = "", feedback: str = "") -> dict:
    try:
        return build_topic_prompt(article, recent_topics, requested_topic, feedback)
    except Exception as exc:
        raise _map_error(exc) from exc


@mcp.tool()
def finance_validate_topic_response(response_text: str, recent_topics: list[str]) -> dict:
    try:
        return validate_topic_response(response_text, recent_topics)
    except Exception as exc:
        raise _map_error(exc) from exc


@mcp.tool()
def finance_get_metadata_generation_prompt(article: str, feedback: str = "") -> dict:
    try:
        return build_metadata_generation_prompt(article, feedback)
    except Exception as exc:
        raise _map_error(exc) from exc


@mcp.tool()
def finance_validate_metadata_response(response_text: str) -> dict:
    try:
        return validate_metadata_response(response_text)
    except Exception as exc:
        raise _map_error(exc) from exc


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
def finance_get_production_outputs(publish_date: str) -> dict:
    """查询某个北京时间计划发布日期的财经成片。"""
    try:
        return {
            "publish_date": publish_date,
            "business_line": MCP_ID,
            "records": list_production_outputs(
                publish_date=publish_date,
                business_line=MCP_ID,
            ),
        }
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
def finance_get_article_prompt(source_text: str, source_hook: str) -> dict:
    """返回正文整理 Prompt；Agent 与 GitHub Runner 必须按原样使用。"""
    try:
        return build_article_prompt(source_text, source_hook)
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
    publish_date: str,
    draft_path: str | None = None,
    cover_highlights: list[str] | None = None,
    intro_scene: str = "",
    content_part: int = 1,
) -> dict:
    """保存完成三类必做改动与措辞级改写的稿件，随后把来源稿件标记为已使用。

    同一天制作第二条时传 content_part=2：缓存与产物目录独立（run-YYYYMMDD-part2），
    D1 落库使用 content_part 区分，run_id 仍为 run-YYYYMMDD。
    """
    try:
        if draft_path is None:
            clean_topic = str(topic or "").strip()
            recent = get_topic(MCP_ID, TOPIC_DEDUPLICATION_DAYS)
            if clean_topic.casefold() in {
                str(item.get("topic") or "").strip().casefold() for item in recent
            }:
                raise WorkflowStepError(
                    f"话题最近 {TOPIC_DEDUPLICATION_DAYS} 天已经发布：{clean_topic}"
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
            publish_date,
            draft_path,
            cover_highlights,
            intro_scene,
            content_part,
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
    material_strategy: str,
) -> dict:
    """生成 TTS 与分镜上下文（同步，易超时）。优先使用 finance_start_storyboard + poll_task。"""
    try:
        return prepare_storyboard(draft_path, tts_config=tts_config, material_strategy=material_strategy)
    except Exception as exc:
        raise _map_error(exc) from exc


@mcp.tool()
def finance_start_storyboard(
    draft_path: str,
    tts_config: dict,
    material_strategy: str,
) -> dict:
    """启动 TTS 与分镜上下文生成；material_strategy 决定分镜写 IMAGE 行还是 VIDEO 行。

    取值：image_library（存量图库选图）、qwen_reference（参考图千问生图）、
    stock_video（Pexels/Pixabay/Coverr 正版实拍视频）。
    立即返回 task_path，用 finance_poll_task 轮询至 done=true。
    """
    try:
        _, draft = load_draft(draft_path, "财经稿件")
        cache_dir = Path(str(draft["cache_dir"]))
        run_id = str(draft["run_id"])

        def _work() -> dict:
            return prepare_storyboard(
                draft_path,
                tts_config=tts_config,
                material_strategy=material_strategy,
            )

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
def finance_start_video_search(
    draft_path: str,
    storyboard_text: str,
    video_config: dict,
) -> dict:
    """stock_video 策略：后台从 Pexels、Pixabay、Coverr 逐镜头搜索实拍视频候选。

    video_config 例：{"orientation": "landscape", "per_provider": 8,
    "providers": ["pexels","pixabay","coverr"], "soft_blur_sigma": 0.55}。
    soft_blur_sigma 控制正文素材的白蒙版磨砂强度，传 0 关闭。
    """
    try:
        _, draft = load_draft(draft_path, "财经稿件")

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
        return {**started, "poll_tool": "finance_poll_task"}
    except Exception as exc:
        raise _map_error(exc) from exc


@mcp.tool()
def finance_get_stock_video_selection_prompt(context_path: str, feedback: str = "") -> dict:
    """返回 Agent 与 GitHub Runner 共用的正版视频候选选择 Prompt。"""
    try:
        return build_stock_video_selection_prompt(context_path, feedback)
    except Exception as exc:
        raise _map_error(exc) from exc


@mcp.tool()
def finance_validate_stock_video_selection_response(context_path: str, response_text: str) -> dict:
    """统一解析并校验 Agent 或千问返回的正版视频选择结果。"""
    try:
        return validate_stock_video_selection_response(context_path, response_text)
    except Exception as exc:
        raise _map_error(exc) from exc


@mcp.tool()
def finance_start_download_videos(context_path: str, selections: list[dict]) -> dict:
    """stock_video 策略：后台下载选择的视频、规范化为与配音一致的镜头并加磨砂。"""
    try:
        resolved_context, context = load_draft(context_path, "正版视频搜索上下文")
        metadata = context.get("metadata")
        if not isinstance(metadata, dict):
            raise WorkflowStepError("正版视频搜索上下文缺少 metadata")
        _, draft = load_draft(str(metadata.get("draft_path") or ""), "财经稿件")

        def _work(progress=None) -> dict:
            return download_selected_videos(resolved_context, selections, progress=progress)

        started = runner_submit_task(
            cache_dir=Path(str(draft["cache_dir"])),
            run_id=str(draft["run_id"]),
            step="download_stock_videos",
            fn=_work,
        )
        return {**started, "poll_tool": "finance_poll_task"}
    except Exception as exc:
        raise _map_error(exc) from exc


@mcp.tool()
def finance_finish_video(
    draft_path: str,
    production_config: dict,
    material_manifest_path: str = "",
    intro_image_path: str = "",
    storyboard_text: str | None = None,
    force_shot_ids: list[str] | None = None,
    production_source: str = "local_mcp",
    image_manifest_path: str = "",
) -> dict:
    """合成成片（同步，易超时）。优先使用 finance_start_finish_video + poll_task。

    material_manifest_path 传选图清单或视频素材清单，按清单内容自动识别素材策略；
    stock_video 策略必须同时传 intro_image_path 指向片头写实图。
    """
    try:
        return finish_finance_video(
            draft_path,
            material_manifest_path=material_manifest_path or image_manifest_path,
            production_config=production_config,
            intro_image_path=intro_image_path or None,
            storyboard_text=storyboard_text,
            force_shot_ids=force_shot_ids,
            production_source=production_source,
        )
    except Exception as exc:
        raise _map_error(exc) from exc


@mcp.tool()
def finance_start_finish_video(
    draft_path: str,
    production_config: dict,
    material_manifest_path: str = "",
    intro_image_path: str = "",
    storyboard_text: str | None = None,
    force_shot_ids: list[str] | None = None,
    production_source: str = "local_mcp",
    image_manifest_path: str = "",
) -> dict:
    """启动成片合成；立即返回 task_path，用 finance_poll_task 轮询至 done=true。"""
    try:
        material_manifest = material_manifest_path or image_manifest_path
        if not material_manifest:
            raise WorkflowStepError("必须传 material_manifest_path（选图清单或视频素材清单）")
        _, draft = load_draft(draft_path, "财经稿件")
        cache_dir = Path(str(draft["cache_dir"]))
        run_id = str(draft["run_id"])

        def _work(progress=None) -> dict:
            return finish_finance_video(
                draft_path,
                material_manifest_path=material_manifest,
                production_config=production_config,
                intro_image_path=intro_image_path or None,
                storyboard_text=storyboard_text,
                force_shot_ids=force_shot_ids,
                production_source=production_source,
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
