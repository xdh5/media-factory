"""逐镜头调用千问生图，并把结果登记到独立财经生成图库。"""

from __future__ import annotations

import json
from pathlib import Path

from core.tools.cloudflare_data import CloudflareDataError, commit_finance_generated_images
from core.tools.generate_image import ImageGenerationError, generate_qwen_image, submit_agent_image_tasks

from .._constants import _PROJECT_ROOT
from .._errors import WorkflowStepError


def _project_relative(path: str | Path) -> str:
    resolved = Path(path).resolve()
    try:
        return resolved.relative_to(_PROJECT_ROOT).as_posix()
    except ValueError as exc:
        raise WorkflowStepError(f"生成图片不在项目目录中：{resolved}") from exc


def _load_context(context_path: str | Path) -> tuple[Path, dict, dict, list[dict], list[str]]:
    resolved_context = Path(context_path).resolve()
    if not resolved_context.is_file():
        raise WorkflowStepError(f"千问生图任务上下文不存在：{resolved_context}")
    try:
        context = json.loads(resolved_context.read_text(encoding="utf-8"))
    except (OSError, json.JSONDecodeError) as exc:
        raise WorkflowStepError(f"读取千问生图任务上下文失败：{resolved_context}。{exc}") from exc
    metadata = context.get("metadata")
    tasks = context.get("tasks")
    if not isinstance(metadata, dict) or metadata.get("image_source") != "qwen_reference":
        raise WorkflowStepError("当前图片任务不是财经千问参考图生图任务")
    if not isinstance(tasks, list) or not tasks:
        raise WorkflowStepError("千问生图任务上下文缺少 tasks")
    image_ids = [str(task.get("image_id") or "") for task in tasks]
    if any(not image_id for image_id in image_ids) or len(set(image_ids)) != len(image_ids):
        raise WorkflowStepError("每张图片必须具有唯一且非空的生图任务 ID")
    return resolved_context, context, metadata, tasks, image_ids


def generate_qwen_shot_images(context_path: str | Path, progress=None) -> dict:
    """生成上下文中的全部镜头图；全部成功后直接写入独立图库。"""
    resolved_context, _, metadata, tasks, image_ids = _load_context(context_path)

    generated = []
    total = len(tasks)
    try:
        for index, task in enumerate(tasks, start=1):
            image_id = str(task["image_id"])
            if progress is not None:
                progress(f"千问生图 {index}/{total}：{image_id}")
            result = generate_qwen_image(
                str(task["prompt"]),
                str(task["output_path"]),
                size=str(task["size"]),
                reference_image_paths=list(task.get("referenced_image_paths") or []),
                cache_signature=str(task.get("cache_signature") or "") or None,
            )
            generated.append({"image_id": image_id, **result})
        manifest = submit_agent_image_tasks(str(resolved_context), [])
    except ImageGenerationError as exc:
        raise WorkflowStepError(exc.message, exc.details) from exc
    captions = metadata.get("caption_by_image_id")
    if not isinstance(captions, dict) or set(captions) != set(image_ids):
        raise WorkflowStepError("图片描述没有完整覆盖全部生图任务")
    records = [
        {
            "caption": str(captions[image_id]),
            "image_path": _project_relative(manifest["images"][image_id]),
        }
        for image_id in image_ids
    ]
    try:
        database = commit_finance_generated_images(records)
    except CloudflareDataError as exc:
        raise WorkflowStepError(exc.message, exc.details) from exc
    if len(database["records"]) != len(tasks):
        raise WorkflowStepError("财经生成图库写入数量与生图任务数量不一致")
    return {
        **manifest,
        "generated": generated,
        "database": database,
        "generated_image_dir": str(metadata.get("generated_image_dir") or ""),
        "generation_task_count": total,
    }
