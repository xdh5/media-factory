"""语言学习 MCP：`python -m core.mcp.language_learning`。"""

from __future__ import annotations

import json
import re
import warnings
from pathlib import Path

warnings.filterwarnings(
    "ignore",
    message=r"Field 'lifespan' has an incomplete definition.*",
)

from mcp.server.fastmcp import FastMCP

from core.tools.clear_cache import ConfirmationRequiredError as ClearCacheConfirmationRequiredError
from core.tools.clear_cache import clear_run
from core.tools.generate_image import (
    ImageGenerationError,
    generate_qwen_image,
    prepare_agent_image_tasks,
    save_agent_image_tasks,
    submit_agent_image_tasks,
)
from core.tools.topic_dedup import TopicDedupError, get_topic

from core.mcp._task_runner import TaskNotFoundError as RunnerTaskNotFoundError
from core.mcp._task_runner import poll_task as runner_poll_task
from core.mcp._task_runner import submit_task as runner_submit_task

from ._constants import (
    SUBJECT_CUTOUT_CACHE_DIR_NAME,
    SUBJECT_GENERATION_MAX_ATTEMPTS,
    SUBJECT_SHEET_IMAGE_ID,
    SUBJECT_SHEET_RADIO,
    SUBJECT_SHEET_SIZE_TEXT,
    MINIMUM_NEW_WORDS,
    TOPIC_DEDUPLICATION_DAYS,
    WORD_HISTORY_DAYS,
    WORKFLOW_ID,
    production_dirs,
    production_run_id,
)
from ._errors import ConfirmationRequiredError, LanguageLearningError, TaskNotFoundError
from .tools import (
    attach_publish_manifest,
    build_subject_sheet_prompt,
    build_vocabulary_prompt,
    compose_fixed_cards,
    create_vocabulary_videos,
    list_recent_words,
    parse_vocabulary_response,
    publish_vocabulary_videos,
    validate_subject_sheet,
    validate_words,
)

mcp = FastMCP(
    "media-factory-language-learning",
    instructions=(
        "语言学习视频编排 MCP。Prompt 由本 MCP 工具返回；TTS 音色、发布账号组等固定参数以 Skill "
        "learn_Chinese_and_Korean 为准，Agent 必须按 Skill 传参。"
        "每期 10 个英语单词中至少 5 个必须未在最近 100 天使用；只有用户触发发布后才记录话题与全部单词。"
        "耗时步骤（千问生图、拼卡、出片、发布）必须用 start + poll_task 轮询，禁止同步调用以免 MCP 超时。"
        "禁止绕过 MCP 自行读写内部文件。"
    ),
)


def _map_error(exc: Exception) -> LanguageLearningError:
    if isinstance(exc, LanguageLearningError):
        return exc
    if isinstance(exc, ImageGenerationError):
        return LanguageLearningError(exc.message, exc.details)
    if isinstance(exc, TopicDedupError):
        return LanguageLearningError(str(exc), exc.details)
    if isinstance(exc, ClearCacheConfirmationRequiredError):
        return ConfirmationRequiredError(str(exc))
    raise exc


def _run_qwen_fallback(context_path: str, failures: list, images: list) -> None:
    """宿主无能力或单张失败三次后，才调用千问。"""
    provided = {str(item.get("image_id") or "").strip() for item in images if isinstance(item, dict)}
    context_file = Path(context_path).resolve()
    context = json.loads(context_file.read_text(encoding="utf-8"))
    tasks = {str(task.get("image_id") or ""): task for task in context.get("tasks") or []}
    seen: set[str] = set()
    for item in failures:
        image_id = str(item["image_id"]).strip()
        if image_id in seen:
            raise LanguageLearningError(f"失败结果重复：{image_id}")
        if image_id in provided:
            raise LanguageLearningError(f"图片 {image_id} 不能同时提交成功路径和失败结果")
        task = tasks[image_id]
        attempts = item.get("attempts", 0)
        if item.get("capability_unavailable") is not True and attempts < 3:
            raise LanguageLearningError(f"图片 {image_id} 仅失败 {attempts} 次；必须尝试满 3 次才能走千问")
        references = task.get("referenced_image_paths") or []
        generate_qwen_image(
            str(task.get("prompt") or ""),
            task["output_path"],
            size=str(task["size"]),
            reference_image_paths=list(references) if isinstance(references, list) else [],
            cache_signature=str(task.get("cache_signature") or "") or None,
        )
        seen.add(image_id)


@mcp.tool()
def language_learning_get_topics() -> dict:
    """返回最近 30 天已占用主题。"""
    try:
        recent = get_topic(WORKFLOW_ID, TOPIC_DEDUPLICATION_DAYS)
        recent_words = list_recent_words()
        return {
            "workflow": WORKFLOW_ID,
            "deduplication_days": TOPIC_DEDUPLICATION_DAYS,
            "recent_topics": [item["topic"] for item in recent],
            "recent_words": recent_words,
            "word_history_days": WORD_HISTORY_DAYS,
            "minimum_new_words": MINIMUM_NEW_WORDS,
            "supported_learning_modes": ["en-zh", "en-ko"],
        }
    except Exception as exc:
        raise _map_error(exc) from exc


@mcp.tool()
def language_learning_occupy_topic(
    topic: str,
    learning_modes: list[str],
) -> dict:
    """创建本次生产目录；正式话题只在用户触发发布后写入 D1。"""
    modes = [str(item).strip() for item in learning_modes if str(item).strip()]
    if not modes:
        raise LanguageLearningError("learning_modes 不能为空")
    clean_topic = str(topic or "").strip()
    if re.fullmatch(r"[A-Za-z]+", clean_topic) is None:
        raise LanguageLearningError("语言学习 topic 必须是一个不含空格的英文单词")
    recent = get_topic(WORKFLOW_ID, TOPIC_DEDUPLICATION_DAYS)
    if clean_topic.casefold() in {
        str(item.get("topic") or "").strip().casefold() for item in recent
    }:
        raise LanguageLearningError(f"语言学习 topic 最近 {TOPIC_DEDUPLICATION_DAYS} 天已经发布：{clean_topic}")
    run_id = production_run_id()
    record_id = int(run_id.removeprefix("run-"))
    cache_root, output_root = production_dirs(run_id)
    cache_root.mkdir(parents=True, exist_ok=True)
    output_root.mkdir(parents=True, exist_ok=True)
    return {
        "topic": clean_topic,
        "learning_modes": modes,
        "topic_record_id": record_id,
        "database_status": "pending_publish",
        "run_id": run_id,
        "cache_dir": str(cache_root),
        "output_dir": str(output_root),
    }


@mcp.tool()
def language_learning_build_vocabulary_prompt(
    topic: str,
    learning_modes: list[str],
) -> dict:
    """返回词表生成 Prompt；Agent 按原样生成纯文本后交给 parse_vocabulary_response。"""
    try:
        return build_vocabulary_prompt(topic, learning_modes, list_recent_words())
    except Exception as exc:
        raise _map_error(exc) from exc


@mcp.tool()
def language_learning_parse_vocabulary_response(
    response_text: str,
    learning_modes: list[str],
    topic: str,
    run_id: str,
) -> dict:
    """严格解析词表并校验最近 100 天新词比例；发布时才记录单词。"""
    try:
        parsed = parse_vocabulary_response(response_text, learning_modes)
        if str(parsed.get("_topic_english") or "").casefold() != str(topic).strip().casefold():
            raise LanguageLearningError("词表英文主题必须与本次单词 TOPIC 完全一致")
        history = validate_words(
            run_id=run_id,
            topic=topic,
            words_by_mode=parsed,
        )
        return {**parsed, "word_history": history}
    except Exception as exc:
        raise _map_error(exc) from exc


@mcp.tool()
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
        prompt += (
            f"\n\n这是第 {generation_attempt} 次生成。上一张图未通过格子位置检查，必须修正：\n- "
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


@mcp.tool()
def language_learning_save_images(context_path: str, images: list[dict]) -> dict:
    """写入已生成的主体图（core.tools.generate_image）。"""
    try:
        return save_agent_image_tasks(context_path, images)
    except ImageGenerationError as exc:
        raise LanguageLearningError(exc.message, exc.details) from exc


@mcp.tool()
def language_learning_submit_images(
    context_path: str,
    images: list[dict],
    failures: list[dict] | None = None,
) -> dict:
    """提交主体图（同步，含千问时易超时）。优先使用 language_learning_start_submit_images + poll_task。"""
    try:
        if failures:
            _run_qwen_fallback(context_path, failures, images or [])
        result = submit_agent_image_tasks(context_path, images or [])
    except ImageGenerationError as exc:
        raise LanguageLearningError(exc.message, exc.details) from exc
    subject_sheet_path = (result.get("images") or {}).get(SUBJECT_SHEET_IMAGE_ID)
    if not subject_sheet_path:
        raise LanguageLearningError(f"提交结果里缺少主体图 {SUBJECT_SHEET_IMAGE_ID}")
    validation = validate_subject_sheet(subject_sheet_path)
    return {**result, "subject_sheet_path": subject_sheet_path, "validation": validation}


def _submit_images_worker(
    context_path: str,
    images: list[dict],
    failures: list[dict] | None,
    cutout_cache_dir: Path,
) -> dict:
    if failures:
        _run_qwen_fallback(context_path, failures, images or [])
    result = submit_agent_image_tasks(context_path, images or [])
    subject_sheet_path = (result.get("images") or {}).get(SUBJECT_SHEET_IMAGE_ID)
    if not subject_sheet_path:
        raise LanguageLearningError(f"提交结果里缺少主体图 {SUBJECT_SHEET_IMAGE_ID}")
    validation = validate_subject_sheet(subject_sheet_path, cutout_cache_dir)
    return {**result, "subject_sheet_path": subject_sheet_path, "validation": validation}


@mcp.tool()
def language_learning_start_submit_images(
    context_path: str,
    images: list[dict],
    run_id: str,
    failures: list[dict] | None = None,
    generation_attempt: int = 1,
) -> dict:
    """启动主体图提交（含可选千问兜底）；立即返回 task_path，用 language_learning_poll_task 轮询。"""
    try:
        cache_root, _ = production_dirs(run_id)
        if generation_attempt < 1 or generation_attempt > SUBJECT_GENERATION_MAX_ATTEMPTS:
            raise LanguageLearningError(
                f"generation_attempt 必须是 1 到 {SUBJECT_GENERATION_MAX_ATTEMPTS}"
            )

        def _work() -> dict:
            return _submit_images_worker(
                context_path,
                images,
                failures,
                cache_root / SUBJECT_CUTOUT_CACHE_DIR_NAME,
            )

        started = runner_submit_task(
            cache_dir=cache_root,
            run_id=run_id,
            step=f"submit_images:{generation_attempt}",
            fn=_work,
        )
        return {**started, "poll_tool": "language_learning_poll_task"}
    except Exception as exc:
        raise _map_error(exc) from exc


@mcp.tool()
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


@mcp.tool()
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

        def _work() -> dict:
            return compose_fixed_cards(
                subject_sheet_path,
                words,
                learning_mode,
                topic_english,
                cache_root / "cards" / learning_mode,
                cutout_cache_dir=cache_root / SUBJECT_CUTOUT_CACHE_DIR_NAME,
            )

        started = runner_submit_task(
            cache_dir=cache_root,
            run_id=run_id,
            step=f"compose_cards:{learning_mode}",
            fn=_work,
        )
        return {**started, "poll_tool": "language_learning_poll_task"}
    except Exception as exc:
        raise _map_error(exc) from exc


@mcp.tool()
def language_learning_create_videos(
    card_dirs: dict[str, str],
    words_by_mode: dict,
    run_id: str,
    voices: dict[str, str],
    publish_config: dict[str, dict],
    topic: str = "",
    language_pause: float = 0.3,
    word_pause: float = 0.3,
) -> dict:
    """TTS + 出片（同步，易超时）。优先使用 language_learning_start_create_videos + poll_task。"""
    try:
        result = create_vocabulary_videos(
            card_dirs,
            words_by_mode,
            run_id,
            topic,
            language_pause,
            word_pause,
            voices=voices,
        )
        return attach_publish_manifest(result, words_by_mode, publish_config)
    except Exception as exc:
        raise _map_error(exc) from exc


@mcp.tool()
def language_learning_start_create_videos(
    card_dirs: dict[str, str],
    words_by_mode: dict,
    run_id: str,
    voices: dict[str, str],
    publish_config: dict[str, dict],
    topic: str = "",
    language_pause: float = 0.3,
    word_pause: float = 0.3,
) -> dict:
    """启动 TTS + 出片；立即返回 task_path，用 language_learning_poll_task 轮询至 done=true。"""
    try:
        cache_root, _ = production_dirs(run_id)

        def _work() -> dict:
            result = create_vocabulary_videos(
                card_dirs,
                words_by_mode,
                run_id,
                topic,
                language_pause,
                word_pause,
                voices=voices,
            )
            return attach_publish_manifest(result, words_by_mode, publish_config)

        started = runner_submit_task(
            cache_dir=cache_root,
            run_id=run_id,
            step="create_videos",
            fn=_work,
        )
        return {**started, "poll_tool": "language_learning_poll_task"}
    except Exception as exc:
        raise _map_error(exc) from exc


@mcp.tool()
def language_learning_publish(manifest_path: str, publish_confirmed: bool) -> dict:
    """兼容旧客户端；非阿里云发布机调用会返回明确错误。"""
    try:
        return publish_vocabulary_videos(manifest_path, publish_confirmed)
    except Exception as exc:
        raise _map_error(exc) from exc


@mcp.tool()
def language_learning_start_publish(manifest_path: str, publish_confirmed: bool, run_id: str) -> dict:
    """兼容旧客户端；正式发布统一使用阿里云发布 Workflow。"""
    try:
        cache_root, _ = production_dirs(run_id)

        def _work() -> dict:
            return publish_vocabulary_videos(manifest_path, publish_confirmed)

        started = runner_submit_task(
            cache_dir=cache_root,
            run_id=run_id,
            step="publish",
            fn=_work,
        )
        return {**started, "poll_tool": "language_learning_poll_task"}
    except Exception as exc:
        raise _map_error(exc) from exc


@mcp.tool()
def language_learning_poll_task(task_path: str) -> dict:
    """轮询后台任务。status=succeeded 时读 result；failed 时读 error 并停止制作。"""
    try:
        return runner_poll_task(task_path=task_path)
    except RunnerTaskNotFoundError as exc:
        raise TaskNotFoundError(str(exc), {"task_path": task_path}) from exc


@mcp.tool()
def language_learning_clear_run(run_id: str, confirmed: bool) -> dict:
    """清本次生产目录（core.tools.clear_cache）。"""
    try:
        return clear_run(WORKFLOW_ID, run_id, confirmed=confirmed)
    except ClearCacheConfirmationRequiredError as exc:
        raise ConfirmationRequiredError(str(exc)) from exc


if __name__ == "__main__":
    mcp.run(transport="stdio")
