"""财经分镜与素材编排。"""
from __future__ import annotations
from pathlib import Path
from ..infrastructure.gateways import ImageGenerationError, save_agent_image_tasks
from ..infrastructure.gateways import runner_submit_task
from ..errors import WorkflowStepError
from ..services.image_delivery import commit_existing_shot_images
from ..services.prepare_videos import download_selected_videos
from ..services.prepare_shot_images import prepare_shot_images
from ..services.prepare_videos import prepare_video_searches
from ..services.save_draft import load_draft
from .common import _map_error

def finance_prepare_images(
    draft_path: str,
    storyboard_text: str,
    image_config: dict,
) -> dict:
    """按 Skill 准备用户参考图宿主生图任务。"""
    try:
        return prepare_shot_images(
            draft_path,
            storyboard_text,
            image_config=image_config,
        )
    except Exception as exc:
        raise _map_error(exc) from exc


def submit_reference_images(context_path: str, images: list[dict]) -> dict:
    """保存宿主图片，校验并登记已完成的镜头素材。"""
    try:
        save_agent_image_tasks(context_path, images)
        return commit_existing_shot_images(context_path)
    except ImageGenerationError as exc:
        raise WorkflowStepError(exc.message, exc.details) from exc
    except Exception as exc:
        raise _map_error(exc) from exc


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
        return started
    except Exception as exc:
        raise _map_error(exc) from exc


def start_download_videos(context_path: str, selections: list[dict] | None = None) -> dict:
    """后台下载实拍素材，返回独立的素材清单。"""
    try:
        resolved_context, context = load_draft(context_path, "正版视频搜索上下文")
        metadata = context.get("metadata")
        if not isinstance(metadata, dict):
            raise WorkflowStepError("正版视频搜索上下文缺少 metadata")
        _, draft = load_draft(str(metadata.get("draft_path") or ""), "财经稿件")

        started = runner_submit_task(
            cache_dir=Path(str(draft["cache_dir"])),
            run_id=str(draft["run_id"]),
            step="download_stock_videos",
            fn=lambda progress: download_selected_videos(resolved_context, selections, progress=progress),
        )
        return {**started, "auto_finish": False, "completion_result": "manifest_path"}
    except Exception as exc:
        raise _map_error(exc) from exc
