"""语言学习后台任务在独立进程中的执行入口。"""

from core.tools.image import ImageGenerationError, submit_agent_image_tasks

from ._constants import SUBJECT_CUTOUT_CACHE_DIR_NAME, SUBJECT_SHEET_IMAGE_ID, production_dirs
from ._errors import LanguageLearningError
from .tools.cards import compose_fixed_cards
from .tools.publish import attach_publish_manifest, publish_vocabulary_videos
from .tools.video import create_vocabulary_videos


def run_job(job_type: str, payload: dict) -> dict:
    if job_type == "submit_images":
        return _submit_images(payload)
    if job_type == "compose_cards":
        return _compose_cards(payload)
    if job_type == "create_videos":
        return _create_videos(payload)
    if job_type == "publish":
        return publish_vocabulary_videos(payload["manifest_path"], payload["publish_confirmed"])
    raise LanguageLearningError(f"不支持的语言学习后台任务类型：{job_type}")


def _submit_images(payload: dict) -> dict:
    try:
        result = submit_agent_image_tasks(
            payload["context_path"],
            payload["images"],
            failures=payload.get("failures"),
        )
    except ImageGenerationError as exc:
        raise LanguageLearningError(exc.message, exc.details) from exc
    subject_sheet_path = (result.get("images") or {}).get(SUBJECT_SHEET_IMAGE_ID)
    if not subject_sheet_path:
        raise LanguageLearningError(
            f"提交结果里缺少主体图 {SUBJECT_SHEET_IMAGE_ID}。请按 prepare 返回的 image_id 提交",
            {"supported_image_ids": [SUBJECT_SHEET_IMAGE_ID]},
        )
    return {**result, "subject_sheet_path": subject_sheet_path, "next_tool": "language_learning_compose_cards"}


def _compose_cards(payload: dict) -> dict:
    run_id = payload["run_id"]
    _run_dir, cache_root, _output_root = production_dirs(run_id)
    card_dir = cache_root / "cards" / payload["learning_mode"]
    result = compose_fixed_cards(
        payload["subject_sheet_path"],
        payload["words"],
        payload["learning_mode"],
        payload["topic_english"],
        card_dir,
        cutout_cache_dir=cache_root / SUBJECT_CUTOUT_CACHE_DIR_NAME,
    )
    return {**result, "run_id": run_id, "next_tool": "language_learning_create_videos"}


def _create_videos(payload: dict) -> dict:
    result = create_vocabulary_videos(
        payload["card_dirs"],
        payload["words_by_mode"],
        payload["run_id"],
        payload.get("topic") or "",
        payload.get("language_pause", 0.3),
        payload.get("word_pause", 0.3),
    )
    return attach_publish_manifest(result, payload["words_by_mode"])
