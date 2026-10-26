"""财经成片交付编排。"""
from __future__ import annotations
from pathlib import Path
from ..infrastructure.gateways import mark_source_script_used
from ..infrastructure.gateways import runner_submit_task
from ..config.settings import MCP_ID
from ..errors import WorkflowStepError
from ..services.assemble_finance_video import finish_finance_video
from ..services.save_draft import save_source_usage
from ..services.upload_to_r2 import upload_finance_assets_to_r2
from ..services.save_draft import load_draft
from .common import _map_error

def _finish_video_and_commit_source_usage(
    draft_path: str,
    **kwargs,
) -> dict:
    """成片成功后才把占用中的数据库原稿标记为已使用。"""
    result = finish_finance_video(draft_path, **kwargs)
    _, draft = load_draft(draft_path, "财经稿件")
    if str(draft.get("source_database_status") or "") != "used":
        usage = mark_source_script_used(
            aweme_id=str(draft["source_aweme_id"]),
            workflow=MCP_ID,
            reservation_token=str(draft["source_reservation_token"]),
            run_id=str(draft["run_id"]),
            source_hook=str(draft["db_source_hook"]),
        )
        save_source_usage(draft_path, usage)
        result["source_usage"] = usage
    return result


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
    stock_video 策略为片头独立选片，提取其原视频首帧制作动画，剩余时长播放片头自己的素材。
    """
    try:
        return _finish_video_and_commit_source_usage(
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
            return _finish_video_and_commit_source_usage(
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


def finance_start_upload_r2(manifest_path: str, run_id: str) -> dict:
    """启动财经成片、封面和生产清单上传 R2。"""
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

