"""把镜头转换为通用宿主 Agent 生图任务；封面由 core.tools.cover 在出片时刻字。"""

from __future__ import annotations

import hashlib
from pathlib import Path

from core.tools.image import prepare_agent_image_tasks, save_agent_image_tasks, submit_agent_image_tasks
from core.tools.image_library import pick_for_shots

from ._constants import STORYBOARD_CONTEXT_FILE_NAME, STORYBOARD_TEXT_FILE_NAME
from ._errors import ConfirmationRequiredError, WorkflowStepError
from ._line import load_line
from .draft import load_draft
from .engine import parse_storyboard, read_prompt


def prepare_agent_images(
    draft_path: str | Path,
    storyboard_text: str,
    *,
    user_confirmed: bool,
    force_image_ids: list[str] | None = None,
    force_images: bool = False,
) -> dict:
    if user_confirmed is not True:
        raise ConfirmationRequiredError("必须先获得用户对完整稿件的明确确认")
    normalized_storyboard = str(storyboard_text or "").strip()
    if not normalized_storyboard:
        raise WorkflowStepError("storyboard_text 不能为空")
    resolved_draft, draft = load_draft(draft_path, "待确认稿件")
    if not draft.get("title") or not str(draft.get("cache_dir") or "").strip():
        raise WorkflowStepError("待确认稿件缺少 title 或 cache_dir")
    line = load_line(str(draft.get("line") or ""))
    cache_root = Path(draft["cache_dir"]).resolve()
    _, storyboard_context = load_draft(cache_root / STORYBOARD_CONTEXT_FILE_NAME, "分镜上下文")
    timeline = storyboard_context.get("timeline")
    if not isinstance(timeline, list) or not timeline:
        raise WorkflowStepError("分镜上下文缺少有效 timeline，请先完成 text2image_prepare_storyboard")
    shots = parse_storyboard(normalized_storyboard, timeline)
    storyboard_path = cache_root / STORYBOARD_TEXT_FILE_NAME
    storyboard_path.write_text(normalized_storyboard, encoding="utf-8")
    shot_image_rules = read_prompt(line.shot_image_rules_path)
    extra_refs = []
    if line.extra_reference_image_path is not None:
        extra_refs = [line.extra_reference_image_path]
    tasks = [
        {
            "image_id": shot["id"],
            "kind": "shot",
            "prompt": f"{shot['prompt']}\n\n{shot_image_rules}",
        }
        for shot in shots
    ]
    metadata = {
        "workflow": line.id,
        "line": line.id,
        "draft_path": str(resolved_draft),
        "storyboard_text": normalized_storyboard,
        "storyboard_path": str(storyboard_path),
        "storyboard_sha256": hashlib.sha256(normalized_storyboard.encode("utf-8")).hexdigest(),
    }
    result = prepare_agent_image_tasks(
        tasks,
        line.visual_style if not line.use_image_library else None,
        line.video_radio,
        line.video_size,
        cache_root / "agent-images",
        additional_reference_image_paths=None if line.use_image_library else extra_refs,
        force_image_ids=force_image_ids,
        force_images=force_images,
        metadata=metadata,
    )
    if line.use_image_library:
        pending = [task for task in result.get("tasks") or [] if task.get("needs_generation")]
        if pending:
            pending_ids = {str(task["image_id"]) for task in pending}
            query_shots = [
                {
                    "image_id": shot["id"],
                    "query": f"{shot['subtitle']}\n{shot['prompt']}",
                }
                for shot in shots
                if shot["id"] in pending_ids
            ]
            picks = pick_for_shots(line.id, query_shots)
            save_agent_image_tasks(
                result["context_path"],
                [{"image_id": item["image_id"], "image_path": item["source_path"]} for item in picks],
            )
            metadata = {**metadata, "image_source": "library", "library_picks": picks}
            result = prepare_agent_image_tasks(
                tasks,
                None,
                line.video_radio,
                line.video_size,
                cache_root / "agent-images",
                additional_reference_image_paths=None,
                force_image_ids=None,
                force_images=False,
                metadata=metadata,
            )
        result["image_source"] = "library"
        result["library_picks"] = list((result.get("metadata") or {}).get("library_picks") or [])
    result["next_tool"] = (
        "text2image_save_images"
        if any(task.get("needs_generation") for task in result.get("tasks") or [])
        else "text2image_submit_images"
    )
    return result


def save_agent_images(context_path: str | Path, images: list[dict]) -> dict:
    result = save_agent_image_tasks(context_path, images)
    result["next_tool"] = "text2image_submit_images" if not result.get("pending_image_ids") else "text2image_save_images"
    return result


def submit_agent_images(
    context_path: str | Path,
    images: list[dict],
    failures: list[dict] | None = None,
) -> dict:
    result = submit_agent_image_tasks(context_path, images, failures=failures)
    result["next_tool"] = "text2image_finish_video"
    return result
