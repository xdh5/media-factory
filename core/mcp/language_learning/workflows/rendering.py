"""词卡、成片和远程交付。"""

from __future__ import annotations


from ..infrastructure import (
    runner_submit_task,
)

from ..config import (
    SUBJECT_CUTOUT_CACHE_DIR_NAME,
    production_dirs,
)
from ..services.subject_cards import compose_fixed_cards, compose_fixed_cards_from_subjects
from ..services.delivery import attach_publish_manifest, upload_publish_assets_to_r2
from ..services.videos import create_vocabulary_videos
from .tasks import _map_error


def language_learning_compose_cards(
    subject_sheet_path: str,
    words: list[dict],
    learning_mode: str,
    topic_english: str,
    run_id: str,
) -> dict:
    """拼单词卡（同步）。优先使用 language_learning_start_compose_cards + poll_task。"""
    cache_root, _ = production_dirs(run_id)
    return compose_fixed_cards(
        subject_sheet_path,
        words,
        learning_mode,
        topic_english,
        cache_root / "cards" / learning_mode,
        cutout_cache_dir=cache_root / SUBJECT_CUTOUT_CACHE_DIR_NAME,
    )


def language_learning_start_compose_cards(
    subject_sheet_path: str,
    words: list[dict],
    learning_mode: str,
    topic_english: str,
    run_id: str,
) -> dict:
    """启动单词卡合成；立即返回 task_path，用 language_learning_poll_task 轮询。"""
    try:
        cache_root, _ = production_dirs(run_id)

        def _work(progress=None) -> dict:
            if progress is not None:
                progress(f"开始拼卡 {learning_mode}")
            return language_learning_compose_cards(subject_sheet_path, words, learning_mode, topic_english, run_id)

        started = runner_submit_task(
            cache_dir=cache_root,
            run_id=run_id,
            step=f"compose_cards:{learning_mode}",
            fn=_work,
        )
        return {**started, "poll_tool": "language_learning_poll_task"}
    except Exception as exc:
        raise _map_error(exc) from exc


def language_learning_start_compose_pack_cards(
    subject_image_paths: list[str], words: list[dict], learning_mode: str, topic_english: str, run_id: str,
) -> dict:
    """使用预制词包的十张已验收透明主体图拼卡，不重复定位和切图。"""
    try:
        cache_root, _ = production_dirs(run_id)
        def _work(progress=None) -> dict:
            if progress is not None: progress(f"开始使用词包拼卡 {learning_mode}")
            return compose_fixed_cards_from_subjects(subject_image_paths, words, learning_mode, topic_english, cache_root / "cards" / learning_mode)
        started = runner_submit_task(cache_dir=cache_root, run_id=run_id, step=f"compose_pack_cards:{learning_mode}", fn=_work)
        return {**started, "poll_tool": "language_learning_poll_task"}
    except Exception as exc:
        raise _map_error(exc) from exc


def _render_with_publish_manifest(
    card_dirs: dict[str, str],
    words_by_mode: dict,
    run_id: str,
    voices: dict[str, str],
    publish_config: dict[str, dict],
    topic: str = "",
    language_pause: float = 0.3,
    word_pause: float = 0.3,
    production_source: str = "local_mcp",
    video_formats: list[str] | None = None,
    countdown_audio_path: str | None = None,
    record_production_outputs: bool = True,
    question_voices: dict[str, str] | None = None,
    *, progress=None, pending_outputs: list[dict] | None = None,
) -> dict:
    result = create_vocabulary_videos(
        card_dirs,
        words_by_mode,
        run_id,
        topic,
        language_pause,
        word_pause,
        production_source,
        video_formats,
        countdown_audio_path,
        record_production_outputs,
        voices=voices,
        question_voices=question_voices,
        progress=progress,
        pending_outputs=pending_outputs,
        hashtags_by_mode={
            mode: list(config.get("tags") or [])
            for mode, config in publish_config.items()
            if isinstance(config, dict)
        },
    )
    return attach_publish_manifest(result, words_by_mode, publish_config)


def language_learning_create_videos(
    card_dirs: dict[str, str],
    words_by_mode: dict,
    run_id: str,
    voices: dict[str, str],
    publish_config: dict[str, dict],
    topic: str = "",
    language_pause: float = 0.3,
    word_pause: float = 0.3,
    production_source: str = "local_mcp",
    video_formats: list[str] | None = None,
    countdown_audio_path: str | None = None,
    record_production_outputs: bool = True,
    question_voices: dict[str, str] | None = None,
) -> dict:
    """TTS + 出片（同步，易超时）。优先使用 language_learning_start_create_videos + poll_task。"""
    try:
        return _render_with_publish_manifest(
            card_dirs, words_by_mode, run_id, voices, publish_config, topic,
            language_pause, word_pause, production_source, video_formats, countdown_audio_path,
            record_production_outputs, question_voices,
        )
    except Exception as exc:
        raise _map_error(exc) from exc


def language_learning_start_create_videos(
    card_dirs: dict[str, str],
    words_by_mode: dict,
    run_id: str,
    voices: dict[str, str],
    publish_config: dict[str, dict],
    topic: str = "",
    language_pause: float = 0.3,
    word_pause: float = 0.3,
    production_source: str = "local_mcp",
    video_formats: list[str] | None = None,
    countdown_audio_path: str | None = None,
    record_production_outputs: bool = True,
    question_voices: dict[str, str] | None = None,
    pending_outputs: list[dict] | None = None,
) -> dict:
    """启动 TTS + 出片；立即返回 task_path，用 language_learning_poll_task 轮询至 done=true。"""
    try:
        cache_root, _ = production_dirs(run_id)

        def _work(progress=None) -> dict:
            if progress is not None:
                progress("开始 TTS 与出片")
            return _render_with_publish_manifest(
                card_dirs, words_by_mode, run_id, voices, publish_config, topic,
                language_pause, word_pause, production_source, video_formats, countdown_audio_path,
                record_production_outputs, question_voices, progress=progress, pending_outputs=pending_outputs,
            )

        started = runner_submit_task(
            cache_dir=cache_root,
            run_id=run_id,
            step="create_videos",
            fn=_work,
        )
        return {**started, "poll_tool": "language_learning_poll_task"}
    except Exception as exc:
        raise _map_error(exc) from exc


def language_learning_start_upload_r2(
    manifest_path: str,
    run_id: str,
    subject_sheet_path: str | None = None,
    learning_modes: list[str] | None = None,
) -> dict:
    """启动语言成片、主题图和发布清单上传 R2。"""
    try:
        cache_root, _ = production_dirs(run_id)

        def _work() -> dict:
            return upload_publish_assets_to_r2(manifest_path, subject_sheet_path, learning_modes)

        started = runner_submit_task(
            cache_dir=cache_root,
            run_id=run_id,
            step="upload_r2",
            fn=_work,
        )
        return {**started, "poll_tool": "language_learning_poll_task"}
    except Exception as exc:
        raise _map_error(exc) from exc
