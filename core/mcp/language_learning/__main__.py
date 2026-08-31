"""语言学习 MCP：`python -m core.mcp.language_learning`。"""

from __future__ import annotations

import json
import os
import re
import warnings
from pathlib import Path

os.environ.setdefault("DASHSCOPE_BUSINESS_LINE", "language_learning")

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
    list_production_outputs,
)
from core.tools.generate_image import (
    ImageGenerationError,
    generate_qwen_image,
    prepare_agent_image_tasks,
    save_agent_image_tasks,
    submit_agent_image_tasks,
)
from core.tools.r2_storage import R2StorageError
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
    build_sheet_validation_prompt,
    build_subject_sheet_prompt,
    build_visual_validation_prompt,
    build_vocabulary_prompt,
    compose_fixed_cards,
    create_vocabulary_videos,
    list_recent_words,
    parse_vocabulary_response,
    prepare_r2_publish_manifest,
    publish_vocabulary_videos,
    review_subject_sheet,
    upload_publish_assets_to_r2,
    validate_subject_sheet,
    validate_words,
)

mcp = FastMCP(
    "media-factory-language-learning",
    instructions=(
        "语言学习视频编排 MCP。交互式生产前必须先向用户确认北京时间计划发布日期 publish_date；"
        "日期不明确时禁止占用话题、创建 run、生产或落库。Prompt 由本 MCP 工具返回；TTS 音色、发布账号组等固定参数以 Skill "
        "learn_Chinese_and_Korean 为准，Agent 必须按 Skill 传参。"
        "每期 10 个英语单词中至少 5 个必须未在最近 100 天使用；只有用户触发发布后才记录话题与全部单词。"
        "文本生成和图片视觉验收由宿主 Agent 完成；千问只用于宿主生图失败后的兜底。"
        "耗时步骤（千问兜底生图、拼卡、出片、发布）必须用 start + poll_task 轮询，禁止同步调用以免 MCP 超时。"
        "默认同时生成原版分段和倒计时问答版，倒计时音轨默认使用仓库 static/countdown.mp3。"
        "中文标题与文件名为 10 Essential {Topic} Words in Chinese；"
        "韩语标题与文件名为 韩语｜{中文词}的韩语怎么说？；问答版不得加 guess 或看图猜词；韩语描述只发 hashtag。"
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
    if isinstance(exc, R2StorageError):
        return LanguageLearningError(exc.message, exc.details)
    if isinstance(exc, ClearCacheConfirmationRequiredError):
        return ConfirmationRequiredError(str(exc))
    if isinstance(exc, CloudflareDataError):
        return LanguageLearningError(exc.message, exc.details)
    raise exc


@mcp.tool()
def language_learning_record_publications(
    publication_id: str,
    run_id: str,
    records: list[dict],
) -> dict:
    """MatrixMedia 发布成功或预约成功后，按最终平台写入语言学习发布记录。"""
    try:
        normalized = [
            {
                **record,
                "publication_id": publication_id,
                "run_id": run_id,
                "business_line": "language_learning",
                "connector": "matrixmedia",
            }
            for record in records
        ]
        return commit_publication_records(normalized)
    except Exception as exc:
        raise _map_error(exc) from exc


@mcp.tool()
def language_learning_get_production_outputs(publish_date: str) -> dict:
    """查询某个北京时间计划发布日期的语言学习成片。"""
    try:
        return {
            "publish_date": publish_date,
            "business_line": WORKFLOW_ID,
            "records": list_production_outputs(
                publish_date=publish_date,
                business_line=WORKFLOW_ID,
            ),
        }
    except Exception as exc:
        raise _map_error(exc) from exc


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
    publish_date: str,
) -> dict:
    """按北京时间计划发布日期创建生产目录；正式话题仅在发布后写入 D1。"""
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
    try:
        run_id = production_run_id(publish_date)
    except ValueError as exc:
        raise LanguageLearningError(str(exc)) from exc
    record_id = int(run_id.removeprefix("run-"))
    cache_root, output_root = production_dirs(run_id)
    cache_root.mkdir(parents=True, exist_ok=True)
    output_root.mkdir(parents=True, exist_ok=True)
    return {
        "topic": clean_topic,
        "learning_modes": modes,
        "topic_record_id": record_id,
        "database_status": "pending_publish",
        "publish_date": str(publish_date).strip(),
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
def language_learning_get_visual_validation_prompt() -> dict:
    """返回宿主 Agent 定位十个主体所需的 Prompt，不做内容质检。"""
    try:
        return build_visual_validation_prompt()
    except Exception as exc:
        raise _map_error(exc) from exc


@mcp.tool()
def language_learning_get_sheet_validation_prompt() -> dict:
    """返回宿主 Agent 检查整张去背景主题图所需的 Prompt。"""
    try:
        return build_sheet_validation_prompt()
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
        has_background_edge = any(
            keyword in issue.casefold()
            for issue in previous_issues
            for keyword in ("background_edge", "背景色", "色边", "描边", "光晕", "毛边")
        )
        retry_instruction = (
            "上一张图抠图后残留背景色边。必须改用一种与上一张明显不同、且与全部主体颜色反差更大的均匀纯色背景，"
            "并禁止主体轮廓出现该背景色描边、光晕或反射污染"
            if has_background_edge
            else "上一张图未通过整图视觉验收，必须修正"
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
    """提交主体图；若需千问兜底，优先使用 start_submit_images + poll_task。"""
    try:
        if failures:
            _run_qwen_fallback(context_path, failures, images or [])
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


def _submit_images_worker(
    context_path: str,
    images: list[dict],
    failures: list[dict] | None,
) -> dict:
    if failures:
        _run_qwen_fallback(context_path, failures, images or [])
    result = submit_agent_image_tasks(context_path, images or [])
    subject_sheet_path = (result.get("images") or {}).get(SUBJECT_SHEET_IMAGE_ID)
    if not subject_sheet_path:
        raise LanguageLearningError(f"提交结果里缺少主体图 {SUBJECT_SHEET_IMAGE_ID}")
    return {
        **result,
        "subject_sheet_path": subject_sheet_path,
        "validation_required": True,
        "next_tool": "language_learning_validate_subject_sheet",
    }


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
def language_learning_validate_subject_sheet(
    subject_sheet_path: str,
    visual_layout: dict,
    run_id: str,
) -> dict:
    """使用宿主 Agent 提交的十个主体框进行验收、去背景和裁图。"""
    try:
        cache_root, _ = production_dirs(run_id)
        return validate_subject_sheet(
            subject_sheet_path,
            visual_layout,
            cache_root / SUBJECT_CUTOUT_CACHE_DIR_NAME,
        )
    except Exception as exc:
        raise _map_error(exc) from exc


@mcp.tool()
def language_learning_review_subject_sheet(
    subject_sheet_path: str,
    review: dict,
    run_id: str,
) -> dict:
    """接收宿主 Agent 对整张去背景主题图的验收结论；未通过时禁止拼卡。"""
    try:
        cache_root, _ = production_dirs(run_id)
        return review_subject_sheet(
            subject_sheet_path,
            cache_root / SUBJECT_CUTOUT_CACHE_DIR_NAME,
            review,
        )
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
    production_source: str = "local_mcp",
    video_formats: list[str] | None = None,
    countdown_audio_path: str | None = None,
    record_production_outputs: bool = True,
    question_voices: dict[str, str] | None = None,
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
            production_source,
            video_formats,
            countdown_audio_path,
            record_production_outputs,
            voices=voices,
            question_voices=question_voices,
            hashtags_by_mode={
                mode: list(config.get("tags") or [])
                for mode, config in publish_config.items()
                if isinstance(config, dict)
            },
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
    production_source: str = "local_mcp",
    video_formats: list[str] | None = None,
    countdown_audio_path: str | None = None,
    record_production_outputs: bool = True,
    question_voices: dict[str, str] | None = None,
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
                production_source,
                video_formats,
                countdown_audio_path,
                record_production_outputs,
                voices=voices,
                question_voices=question_voices,
                hashtags_by_mode={
                    mode: list(config.get("tags") or [])
                    for mode, config in publish_config.items()
                    if isinstance(config, dict)
                },
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
def language_learning_start_upload_r2(
    manifest_path: str,
    run_id: str,
    subject_sheet_path: str | None = None,
) -> dict:
    """启动语言成片、主题图和发布清单上传 R2。"""
    try:
        cache_root, _ = production_dirs(run_id)

        def _work() -> dict:
            return upload_publish_assets_to_r2(manifest_path, subject_sheet_path)

        started = runner_submit_task(
            cache_dir=cache_root,
            run_id=run_id,
            step="upload_r2",
            fn=_work,
        )
        return {**started, "poll_tool": "language_learning_poll_task"}
    except Exception as exc:
        raise _map_error(exc) from exc


@mcp.tool()
def language_learning_start_publish(
    manifest_path: str,
    publish_confirmed: bool,
    run_id: str,
    targets: list[str] | None = None,
    publish_at: str | None = None,
    publish_at_by_target: dict[str, str | None] | None = None,
    video_parts: list[int] | None = None,
) -> dict:
    """启动中文官方平台发布；立即返回 task_path，用 language_learning_poll_task 轮询。"""
    try:
        cache_root, _ = production_dirs(run_id)

        def _work() -> dict:
            resolved_manifest_path = manifest_path
            if str(manifest_path).strip().startswith(("http://", "https://")):
                resolved_manifest_path = prepare_r2_publish_manifest(
                    manifest_path,
                    run_id,
                    cache_root,
                )
            return publish_vocabulary_videos(
                resolved_manifest_path,
                publish_confirmed,
                targets=targets,
                publish_at=publish_at,
                publish_at_by_target=publish_at_by_target,
                video_parts=video_parts,
            )

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
