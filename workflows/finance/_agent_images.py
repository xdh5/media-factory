"""把 Finance 封面和镜头转换为通用宿主 Agent 生图任务。"""

from __future__ import annotations

import hashlib
import json
from pathlib import Path

from core.tools.image import prepare_agent_image_tasks, submit_agent_image_tasks

from ._constants import (
    COVER_PROMPT_PATH,
    FINANCE_REFERENCE_IMAGE_PATH,
    SHOT_IMAGE_RULES_PATH,
    STORYBOARD_CONTEXT_FILE_NAME,
    VIDEO_RADIO,
    VIDEO_SIZE,
    VISUAL_STYLE,
)
from ._errors import ConfirmationRequiredError, DraftNotFoundError, WorkflowStepError
from .workflow import _parse_storyboard, _read_prompt, _render


def _load_json(path: str | Path, label: str) -> tuple[Path, dict]:
    resolved = Path(path).resolve()
    if not resolved.is_file():
        raise DraftNotFoundError(f"{label}不存在：{resolved}", {"path": str(resolved)})
    try:
        value = json.loads(resolved.read_text(encoding="utf-8"))
    except (OSError, json.JSONDecodeError) as exc:
        raise WorkflowStepError(f"读取{label}失败：{resolved}。{exc}") from exc
    if not isinstance(value, dict):
        raise WorkflowStepError(f"{label}必须是 JSON 对象：{resolved}")
    return resolved, value


def prepare_agent_images(
    draft_path: str | Path,
    storyboard_text: str,
    *,
    user_confirmed: bool,
    force_image_ids: list[str] | None = None,
    force_images: bool = False,
) -> dict:
    """只组装 Finance 业务提示词，缓存和参考图逻辑由通用生图 Tool 处理。"""
    if user_confirmed is not True:
        raise ConfirmationRequiredError("必须先获得用户对完整稿件的明确确认")
    normalized_storyboard = str(storyboard_text or "").strip()
    if not normalized_storyboard:
        raise WorkflowStepError("storyboard_text 不能为空")
    resolved_draft, draft = _load_json(draft_path, "待确认稿件")
    if not draft.get("title") or not str(draft.get("cache_dir") or "").strip():
        raise WorkflowStepError("待确认稿件缺少 title 或 cache_dir")
    cache_root = Path(draft["cache_dir"]).resolve()
    _, storyboard_context = _load_json(cache_root / STORYBOARD_CONTEXT_FILE_NAME, "分镜上下文")
    timeline = storyboard_context.get("timeline")
    if not isinstance(timeline, list) or not timeline:
        raise WorkflowStepError("分镜上下文缺少有效 timeline，请先完成 finance_prepare_storyboard")
    shots = _parse_storyboard(normalized_storyboard, timeline)
    cover_prompt = _render(
        _read_prompt(COVER_PROMPT_PATH),
        size=VIDEO_SIZE,
        radio=VIDEO_RADIO,
        title=draft["title"],
        style=VISUAL_STYLE,
    )
    shot_image_rules = _read_prompt(SHOT_IMAGE_RULES_PATH)
    tasks = [{"image_id": "cover", "kind": "cover", "prompt": cover_prompt}]
    tasks.extend(
        {
            "image_id": shot["id"],
            "kind": "shot",
            "prompt": f"{shot['prompt']}\n\n{shot_image_rules}",
        }
        for shot in shots
    )
    result = prepare_agent_image_tasks(
        tasks,
        VISUAL_STYLE,
        VIDEO_RADIO,
        VIDEO_SIZE,
        cache_root / "agent-images",
        additional_reference_image_paths=[FINANCE_REFERENCE_IMAGE_PATH],
        force_image_ids=force_image_ids,
        force_images=force_images,
        metadata={
            "workflow": "finance",
            "draft_path": str(resolved_draft),
            "storyboard_sha256": hashlib.sha256(normalized_storyboard.encode("utf-8")).hexdigest(),
        },
    )
    result["next_tool"] = "finance_submit_images"
    return result


def submit_agent_images(
    context_path: str | Path,
    images: list[dict],
    failures: list[dict] | None = None,
) -> dict:
    """把当前 Agent 图片交给通用生图 Tool 校验并缓存。"""
    result = submit_agent_image_tasks(context_path, images, failures=failures)
    result["next_tool"] = "finance_finish_video"
    return result
