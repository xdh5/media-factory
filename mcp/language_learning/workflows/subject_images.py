"""主体图任务、切图定位和验收。"""

from __future__ import annotations


from workflows.language_learning.parameters import SUBJECT_CUTOUT_CACHE_DIR_NAME, production_dirs
from media_factory_mcp.language_learning.services.subject_cutouts import (
    review_subject_sheet, validate_subject_sheet,
)
from media_factory_mcp.language_learning.services.prompt_service import (
    build_sheet_validation_prompt, build_visual_validation_prompt,
)
from .tasks import _map_error


def language_learning_get_visual_validation_prompt() -> dict:
    """返回宿主 Agent 定位十个主体所需的 Prompt，不做内容质检。"""
    try:
        return build_visual_validation_prompt()
    except Exception as exc:
        raise _map_error(exc) from exc


def language_learning_get_sheet_validation_prompt() -> dict:
    """返回宿主 Agent 检查十张透明切图整体验收图所需的 Prompt。"""
    try:
        return build_sheet_validation_prompt()
    except Exception as exc:
        raise _map_error(exc) from exc


def language_learning_validate_subject_sheet(
    subject_sheet_path: str,
    visual_layout: dict,
    run_id: str,
) -> dict:
    """硬校验真实透明主题图，并按宿主 Agent 提交的十个主体框裁图。"""
    try:
        cache_root, _ = production_dirs(run_id)
        return validate_subject_sheet(
            subject_sheet_path,
            visual_layout,
            cache_root / SUBJECT_CUTOUT_CACHE_DIR_NAME,
        )
    except Exception as exc:
        raise _map_error(exc) from exc


def language_learning_review_subject_sheet(
    subject_sheet_path: str,
    review: dict,
    run_id: str,
) -> dict:
    """接收宿主 Agent 对十张透明切图整体验收图的结论；未通过时禁止拼卡。"""
    try:
        cache_root, _ = production_dirs(run_id)
        return review_subject_sheet(
            subject_sheet_path,
            cache_root / SUBJECT_CUTOUT_CACHE_DIR_NAME,
            review,
        )
    except Exception as exc:
        raise _map_error(exc) from exc
