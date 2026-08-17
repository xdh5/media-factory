"""供 Trae 通过 MCP 分阶段编排 Finance 工作流。"""

from __future__ import annotations

import json
from pathlib import Path

from core.tools.matrixmedia import list_account_groups, publish_to_group
from core.tools.topic_history import recent_topics, reserve_topic, update_topic_status
from core.tools.tts.compose import compose as compose_tts

from ._constants import (
    DEFAULT_CACHE_ROOT,
    DEFAULT_DATABASE_PATH,
    DEFAULT_OUTPUT_ROOT,
    DEFAULT_PUBLISH_ACCOUNT_GROUP,
    DRAFT_FILE_NAME,
    FINANCE_PROMPT_PATH,
    FORMAT_PROMPT_PATH,
    STORYBOARD_CONTEXT_FILE_NAME,
    TEXT2IMAGE_PROMPT_PATH,
    TOPIC_DEDUPLICATION_DAYS,
    TTS_VOICE,
    VIDEO_RADIO,
    VIDEO_SIZE,
    VISUAL_STYLE,
    WORKFLOW_ID,
)
from ._errors import ConfirmationRequiredError, DraftNotFoundError, WorkflowStepError
from .workflow import _parse_metadata, _read_prompt, _render, _timeline_table, run_finance_workflow


def _load_json(path: str | Path, label: str) -> tuple[Path, dict]:
    resolved = Path(path).resolve()
    if not resolved.is_file():
        raise DraftNotFoundError(f"{label}不存在：{resolved}", {"path": str(resolved)})
    try:
        payload = json.loads(resolved.read_text(encoding="utf-8"))
    except (OSError, json.JSONDecodeError) as exc:
        raise WorkflowStepError(f"读取{label}失败：{resolved}。{exc}") from exc
    if not isinstance(payload, dict):
        raise WorkflowStepError(f"{label}必须是 JSON 对象：{resolved}")
    return resolved, payload


def get_draft_context(database_path: str | Path | None = None) -> dict:
    """返回 Trae 生成选题、正文和标题标签所需的上下文。"""
    database = Path(database_path or DEFAULT_DATABASE_PATH).resolve()
    recent = recent_topics(database, WORKFLOW_ID, TOPIC_DEDUPLICATION_DAYS)
    return {
        "workflow": WORKFLOW_ID,
        "deduplication_days": TOPIC_DEDUPLICATION_DAYS,
        "recent_topics": [item["topic"] for item in recent],
        "article_prompt_template": _read_prompt(FINANCE_PROMPT_PATH),
        "metadata_prompt": _read_prompt(FORMAT_PROMPT_PATH),
        "next_tool": "finance_save_draft",
    }


def save_draft(
    topic: str,
    article: str,
    title: str,
    short_title: str,
    hashtags: list[str],
    database_path: str | Path | None = None,
    draft_path: str | Path | None = None,
) -> dict:
    """保存 Trae 生成的稿件，并停在用户稿件确认节点。"""
    normalized_topic = str(topic or "").strip()
    normalized_article = str(article or "").strip()
    if not normalized_topic:
        raise WorkflowStepError("topic 不能为空")
    if not normalized_article:
        raise WorkflowStepError("article 不能为空")
    if not isinstance(hashtags, list):
        raise WorkflowStepError("hashtags 必须是包含四个标签的列表")
    metadata_line = "|".join([str(title), str(short_title), *(str(item) for item in hashtags)])
    metadata = _parse_metadata(metadata_line)
    database = Path(database_path or DEFAULT_DATABASE_PATH).resolve()
    if draft_path is not None:
        resolved_draft, existing = _load_json(draft_path, "待修改稿件")
        if normalized_topic != str(existing.get("topic") or "").strip():
            raise WorkflowStepError("修改已有稿件时不能更换话题；请重新开始一次 Finance 工作流")
        record = {"id": int(existing["topic_record_id"]), "topic": normalized_topic}
        run_id = str(existing["run_id"])
        cache_root = Path(existing["cache_dir"]).resolve()
        output_root = Path(existing["output_dir"]).resolve()
        target_draft_path = resolved_draft
    else:
        record = reserve_topic(database, WORKFLOW_ID, normalized_topic, TOPIC_DEDUPLICATION_DAYS)
        run_id = f"run-{record['id']:06d}"
        cache_root = (DEFAULT_CACHE_ROOT / run_id).resolve()
        output_root = (DEFAULT_OUTPUT_ROOT / run_id).resolve()
        target_draft_path = cache_root / DRAFT_FILE_NAME
    cache_root.mkdir(parents=True, exist_ok=True)
    output_root.mkdir(parents=True, exist_ok=True)
    draft = {
        "version": 1,
        "status": "awaiting_article_confirmation",
        "confirmation_required": "article",
        "database_path": str(database),
        "topic": record["topic"],
        "run_id": run_id,
        "topic_record_id": record["id"],
        "article": normalized_article,
        **metadata,
        "cache_dir": str(cache_root),
        "output_dir": str(output_root),
        "draft_path": str(target_draft_path),
    }
    target_draft_path.write_text(json.dumps(draft, ensure_ascii=False, indent=2), encoding="utf-8")
    return draft


def prepare_storyboard(draft_path: str | Path, *, user_confirmed: bool) -> dict:
    """用户确认稿件后生成 TTS，并返回让 Trae 生成分镜的完整提示。"""
    if user_confirmed is not True:
        raise ConfirmationRequiredError("必须先获得用户对完整稿件的明确确认")
    resolved_draft, draft = _load_json(draft_path, "待确认稿件")
    for key in ("article", "cache_dir", "topic_record_id"):
        if not draft.get(key):
            raise WorkflowStepError(f"待确认稿件缺少字段：{key}")
    cache_root = Path(draft["cache_dir"]).resolve()
    tts_path = cache_root / "narration.wav"
    tts_result = compose_tts(str(draft["article"]), tts_path, TTS_VOICE)
    storyboard_prompt = _render(
        _read_prompt(TEXT2IMAGE_PROMPT_PATH),
        style=VISUAL_STYLE,
        radio=VIDEO_RADIO,
        size=VIDEO_SIZE,
    ) + "\n\n" + _timeline_table(tts_result["timeline"])
    context_path = cache_root / STORYBOARD_CONTEXT_FILE_NAME
    context = {
        "status": "awaiting_storyboard",
        "draft_path": str(resolved_draft),
        "storyboard_prompt": storyboard_prompt,
        "timeline": tts_result["timeline"],
        "tts_path": tts_result["output_path"],
        "next_tool": "finance_finish_video",
    }
    context_path.write_text(json.dumps(context, ensure_ascii=False, indent=2), encoding="utf-8")
    context["context_path"] = str(context_path)
    return context


def finish_video(
    draft_path: str | Path,
    storyboard_text: str,
    *,
    user_confirmed: bool,
    force_shot_ids: list[str] | None = None,
    force_images: bool = False,
) -> dict:
    """使用 Trae 生成的分镜自动完成视频，并停在发布确认节点。"""
    if user_confirmed is not True:
        raise ConfirmationRequiredError("必须先获得用户对完整稿件的明确确认")
    resolved_draft, draft = _load_json(draft_path, "待确认稿件")
    return run_finance_workflow(
        database_path=draft.get("database_path") or DEFAULT_DATABASE_PATH,
        draft_path=resolved_draft,
        article_confirmed=True,
        storyboard_text=storyboard_text,
        force_shot_ids=force_shot_ids,
        force_images=force_images,
    )


def publish_product(
    manifest_path: str | Path,
    *,
    publish_confirmed: bool,
    account_group_name: str = DEFAULT_PUBLISH_ACCOUNT_GROUP,
) -> dict:
    """用户确认发布后，把 Finance 成品发布到指定 MatrixMedia 账号组。"""
    if publish_confirmed is not True:
        raise ConfirmationRequiredError("必须先获得用户对本次成品发布的明确确认")
    _, manifest = _load_json(manifest_path, "Finance 成品清单")
    for key in ("video_path", "title", "short_title", "hashtags", "topic_record_id"):
        if not manifest.get(key):
            raise WorkflowStepError(f"Finance 成品清单缺少字段：{key}")
    group = next(
        (item for item in list_account_groups() if item["name"] == account_group_name),
        None,
    )
    if group is None:
        raise WorkflowStepError(f"MatrixMedia 账号组不存在：{account_group_name}")
    result = publish_to_group(
        group["id"],
        manifest["video_path"],
        manifest["title"],
        short_title=manifest["short_title"],
        tags=list(manifest["hashtags"]),
        task_name=manifest.get("run_id"),
    )
    if result.get("success"):
        update_topic_status(
            manifest.get("database_path") or DEFAULT_DATABASE_PATH,
            int(manifest["topic_record_id"]),
            "published",
        )
    return result
