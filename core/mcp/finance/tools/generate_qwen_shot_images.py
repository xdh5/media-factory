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


def _commit_generated_images(
    resolved_context: Path,
    metadata: dict,
    tasks: list[dict],
    image_ids: list[str],
    *,
    generated: list[dict],
    recovered_existing_images: bool,
) -> dict:
    manifest = submit_agent_image_tasks(str(resolved_context), [])
    captions = metadata.get("caption_by_image_id")
    if not isinstance(captions, dict) or set(captions) != set(image_ids):
        raise WorkflowStepError("图片描述没有完整覆盖全部生图任务")
    library_ids = metadata.get("library_id_by_image_id")
    if not isinstance(library_ids, dict) or set(library_ids) != set(image_ids):
        raise WorkflowStepError("图库编号没有完整覆盖全部生图任务")
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
    expected_ids = [int(library_ids[image_id]) for image_id in image_ids]
    saved_ids = [int(record["id"]) for record in database["records"]]
    if saved_ids != expected_ids:
        raise WorkflowStepError(
            "财经生成图库的 D1 编号与本地图片编号不一致",
            {"expected_ids": expected_ids, "saved_ids": saved_ids},
        )
    return {
        **manifest,
        "generated": generated,
        "database": database,
        "generated_image_dir": str(metadata.get("generated_image_dir") or ""),
        "generation_task_count": len(tasks),
        "recovered_existing_images": recovered_existing_images,
    }


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
    except ImageGenerationError as exc:
        raise WorkflowStepError(exc.message, exc.details) from exc
    return _commit_generated_images(
        resolved_context,
        metadata,
        tasks,
        image_ids,
        generated=generated,
        recovered_existing_images=False,
    )


def commit_existing_qwen_shot_images(context_path: str | Path) -> dict:
    """校验上下文中的现有镜头图并直接写入 D1，绝不调用生图服务。"""
    resolved_context, _, metadata, tasks, image_ids = _load_context(context_path)
    missing_paths = [
        str(Path(str(task.get("output_path") or "")).resolve())
        for task in tasks
        if not Path(str(task.get("output_path") or "")).resolve().is_file()
    ]
    if missing_paths:
        raise WorkflowStepError(
            "现有镜头图不完整，禁止跳过生图直接入库",
            {"missing_paths": missing_paths},
        )
    return _commit_generated_images(
        resolved_context,
        metadata,
        tasks,
        image_ids,
        generated=[],
        recovered_existing_images=True,
    )
