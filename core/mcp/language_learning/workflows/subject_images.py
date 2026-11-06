"""主体图任务、切图定位和验收。"""

from __future__ import annotations


from ..infrastructure import (
    ImageGenerationError,
    prepare_agent_image_tasks,
    runner_submit_task,
    save_agent_image_tasks,
    submit_agent_image_tasks,
)

from ..config import (
    SUBJECT_CUTOUT_CACHE_DIR_NAME,
    SUBJECT_GENERATION_MAX_ATTEMPTS,
    SUBJECT_SHEET_IMAGE_ID,
    SUBJECT_SHEET_RADIO,
    SUBJECT_SHEET_SIZE_TEXT,
    WORKFLOW_ID,
    production_dirs,
)
from ..errors import LanguageLearningError
from ..services.subject_cutouts import (
    review_subject_sheet, validate_subject_sheet,
)
from ..services.prompt_service import (
    build_sheet_validation_prompt, build_subject_sheet_prompt, build_visual_validation_prompt,
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


def language_learning_prepare_images(
    topic: str,
    words: list[dict],
    run_id: str,
    force_images: bool = False,
    generation_attempt: int = 1,
    validation_issues: list[str] | None = None,
) -> dict:
    """注册主体图生图任务（core.tools.generate_image）。"""
    try:
        sheet = build_subject_sheet_prompt(topic, words)
    except Exception as exc:
        raise _map_error(exc) from exc
    prompt = str(sheet.get("subject_sheet_prompt") or "").strip()
    if not prompt:
        raise LanguageLearningError("主体图 Prompt 生成失败")
    if generation_attempt < 1 or generation_attempt > SUBJECT_GENERATION_MAX_ATTEMPTS:
        raise LanguageLearningError(
            f"generation_attempt 必须是 1 到 {SUBJECT_GENERATION_MAX_ATTEMPTS}"
        )
    previous_issues = [str(item).strip() for item in validation_issues or [] if str(item).strip()]
    if previous_issues:
        retry_instruction = (
            "上一张图未通过整图视觉验收，必须修正"
        )
        prompt += (
            f"\n\n这是第 {generation_attempt} 次生成。{retry_instruction}：\n- "
            + "\n- ".join(previous_issues)
        )
    cache_root, _ = production_dirs(run_id)
    try:
        return prepare_agent_image_tasks(
            [{"image_id": SUBJECT_SHEET_IMAGE_ID, "kind": "image", "prompt": prompt}],
            None,
            SUBJECT_SHEET_RADIO,
            SUBJECT_SHEET_SIZE_TEXT,
            cache_root / "agent-images",
            force_images=force_images,
            metadata={
                "workflow": WORKFLOW_ID,
                "topic": topic,
                "run_id": run_id,
                "generation_attempt": generation_attempt,
            },
        )
    except ImageGenerationError as exc:
        raise LanguageLearningError(exc.message, exc.details) from exc


def language_learning_save_images(context_path: str, images: list[dict]) -> dict:
    """写入已生成的主体图（core.tools.generate_image）。"""
    try:
        return save_agent_image_tasks(context_path, images)
    except ImageGenerationError as exc:
        raise LanguageLearningError(exc.message, exc.details) from exc


def language_learning_submit_images(
    context_path: str,
    images: list[dict],
) -> dict:
    """提交宿主生成的主体图并校验产物。"""
    try:
        result = submit_agent_image_tasks(context_path, images or [])
    except ImageGenerationError as exc:
        raise LanguageLearningError(exc.message, exc.details) from exc
    subject_sheet_path = (result.get("images") or {}).get(SUBJECT_SHEET_IMAGE_ID)
    if not subject_sheet_path:
        raise LanguageLearningError(f"提交结果里缺少主体图 {SUBJECT_SHEET_IMAGE_ID}")
    return {
        **result,
        "subject_sheet_path": subject_sheet_path,
        "validation_required": True,
        "next_tool": "language_learning_validate_subject_sheet",
    }


def language_learning_start_submit_images(
    context_path: str,
    images: list[dict],
    run_id: str,
    generation_attempt: int = 1,
) -> dict:
    """启动宿主主体图提交；立即返回 task_path，用 language_learning_poll_task 轮询。"""
    try:
        cache_root, _ = production_dirs(run_id)
        if generation_attempt < 1 or generation_attempt > SUBJECT_GENERATION_MAX_ATTEMPTS:
            raise LanguageLearningError(
                f"generation_attempt 必须是 1 到 {SUBJECT_GENERATION_MAX_ATTEMPTS}"
            )

        def _work(progress=None) -> dict:
            if progress is not None:
                progress("正在提交宿主生成的主体图")
            return language_learning_submit_images(context_path, images)

        started = runner_submit_task(
            cache_dir=cache_root,
            run_id=run_id,
            step=f"submit_images:{generation_attempt}",
            fn=_work,
        )
        return {**started, "poll_tool": "language_learning_poll_task"}
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
