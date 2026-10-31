"""财经分镜与素材编排。"""
from __future__ import annotations
from copy import deepcopy
from pathlib import Path
from ..infrastructure.gateways import ImageGenerationError, save_agent_image_tasks, submit_agent_image_tasks
from ..infrastructure.gateways import runner_submit_task
from ..config.settings import DEFAULT_PRODUCTION_CONFIG
from ..errors import WorkflowStepError
from ..services.prepare_videos import build_stock_video_selection_prompt
from ..services.generate_qwen_shot_images import commit_existing_qwen_shot_images
from ..services.prepare_videos import download_selected_videos
from ..services.generate_qwen_shot_images import generate_qwen_shot_images
from ..services.prepare_shot_images import prepare_shot_images
from ..services.storyboard import prepare_storyboard
from ..services.prepare_videos import prepare_video_searches
from ..services.prepare_videos import validate_stock_video_selection_response
from ..services.save_draft import load_draft
from .common import _map_error
from .delivery import _finish_video_and_commit_source_usage

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


def finance_start_storyboard(
    draft_path: str,
    tts_config: dict,
    material_strategy: str,
) -> dict:
    """启动 TTS 与分镜上下文生成；material_strategy 决定分镜写 IMAGE 行还是 VIDEO 行。

    取值：stock_video（Pexels/Pixabay/Coverr 正版实拍视频）、
    qwen_reference（参考图千问生图）。
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


def finance_prepare_images(
    draft_path: str,
    storyboard_text: str,
    image_config: dict,
) -> dict:
    """按 Skill 准备用户参考图千问生图任务。"""
    try:
        return prepare_shot_images(
            draft_path,
            storyboard_text,
            image_config=image_config,
        )
    except Exception as exc:
        raise _map_error(exc) from exc


def finance_save_images(context_path: str, images: list[dict]) -> dict:
    """把已生成的图片立刻写入本次生产缓存。"""
    try:
        return save_agent_image_tasks(context_path, images)
    except ImageGenerationError as exc:
        raise WorkflowStepError(exc.message, exc.details) from exc


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


def finance_commit_existing_images(context_path: str) -> dict:
    """仅校验现有镜头图片并写入 D1；绝不重新调用千问生图。"""
    try:
        return commit_existing_qwen_shot_images(context_path)
    except Exception as exc:
        raise _map_error(exc) from exc


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


def finance_get_stock_video_selection_prompt(context_path: str, feedback: str = "") -> dict:
    """返回 Agent 与 GitHub Runner 共用的正版视频候选选择 Prompt。"""
    try:
        return build_stock_video_selection_prompt(context_path, feedback)
    except Exception as exc:
        raise _map_error(exc) from exc


def finance_validate_stock_video_selection_response(context_path: str, response_text: str) -> dict:
    """统一解析并校验 Agent 或千问返回的正版视频选择结果。"""
    try:
        return validate_stock_video_selection_response(context_path, response_text)
    except Exception as exc:
        raise _map_error(exc) from exc


def finance_start_download_videos(
    context_path: str,
    selections: list[dict] | None = None,
    auto_finish: bool = True,
    production_config: dict | None = None,
    production_source: str = "local_mcp",
) -> dict:
    """后台下载并自动合成，轮询同一 task_path 至 done=true 获取 video_path。

    默认读取统一成片配置；自动合成前须传入宿主定稿的重点句 groups、英文字幕 translations 和章节 titles。先调用 finance_get_video_editorial_input 获取输入。
    单段不足时拼两段，下载和合成均复用缓存。只有 auto_finish=false 时仅返回素材清单。
    自动合成失败可重试本工具或调用 finance_start_finish_video，无需重复处理完成镜头。
    本工具不上传 R2、不发布平台。
    """
    try:
        resolved_context, context = load_draft(context_path, "正版视频搜索上下文")
        metadata = context.get("metadata")
        if not isinstance(metadata, dict):
            raise WorkflowStepError("正版视频搜索上下文缺少 metadata")
        _, draft = load_draft(str(metadata.get("draft_path") or ""), "财经稿件")
        if production_source not in {"local_mcp", "github_workflow"}:
            raise WorkflowStepError("production_source 必须是 local_mcp 或 github_workflow")
        if production_config is not None and not isinstance(production_config, dict):
            raise WorkflowStepError("production_config 必须是对象")
        settings = deepcopy(DEFAULT_PRODUCTION_CONFIG["production_config"])
        settings.update(deepcopy(production_config or {}))
        if auto_finish:
            from ..services.video_editorial import validate_video_editorial
            validate_video_editorial(str(metadata["draft_path"]), str(metadata["storyboard_text"]), settings)


        def _work(progress=None) -> dict:
            materials = download_selected_videos(resolved_context, selections, progress=progress)
            if not auto_finish:
                return materials
            if progress:
                progress("视频素材已就绪，正在自动合成最终成片")
            result = _finish_video_and_commit_source_usage(
                str(metadata["draft_path"]),
                material_manifest_path=materials["manifest_path"],
                production_config=settings,
                storyboard_text=metadata.get("storyboard_text"),
                production_source=production_source,
                progress=progress,
            )
            return {**result, "material_manifest_path": materials["manifest_path"], "auto_finished": True}

        started = runner_submit_task(
            cache_dir=Path(str(draft["cache_dir"])),
            run_id=str(draft["run_id"]),
            step="download_and_finish_video" if auto_finish else "download_stock_videos",
            fn=_work,
        )
        return {**started, "poll_tool": "finance_poll_task", "auto_finish": auto_finish,
                "completion_result": "video_path" if auto_finish else "manifest_path"}
    except Exception as exc:
        raise _map_error(exc) from exc

