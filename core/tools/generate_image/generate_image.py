"""把任意工作流的图片任务交给当前宿主 Agent 生图，并接收本地结果。"""

from __future__ import annotations

import json
import hashlib
import re
from pathlib import Path
from uuid import uuid4

from PIL import Image

from ._constants import (
    AGENT_IMAGE_CONTEXT_NAME,
    AGENT_IMAGE_MANIFEST_NAME,
    AGENT_IMAGE_TASK_VERSION,
)
from ._errors import AgentImageTaskError, InvalidParameterError, ReferenceImageError
from ._select_style import _select_style
from ._image import _fit_image, _validate_dimensions, _write_png

__all__ = ["prepare_agent_image_tasks", "save_agent_image_tasks", "submit_agent_image_tasks"]


def _agent_path(path: Path) -> str:
    """返回适合跨 Agent JSON Tool 调用的绝对路径，避免 Windows 反斜杠二次转义。"""
    return path.resolve().as_posix()


def _valid_image(path: Path, width: int, height: int, cache_signature: str | None = None) -> bool:
    if not path.is_file():
        return False
    try:
        with Image.open(path) as image:
            image.verify()
        if cache_signature is None:
            return True
        metadata_path = path.with_suffix(".json")
        if not metadata_path.is_file():
            return False
        metadata = json.loads(metadata_path.read_text(encoding="utf-8"))
        return metadata.get("cache_signature") == cache_signature
    except (OSError, ValueError):
        return False


def _final_prompt(
    prompt: str,
    style: dict | None,
    radio: str,
    size: str,
    *,
    has_references: bool,
) -> str:
    parts = [prompt.strip()]
    if style:
        parts.append(f"画风要求：{style['description']}")
    if has_references:
        parts.append(
            "随附图片均为视觉参考图。"
            + ("第一张用于参考画法、笔触、材质、光影和配色；" if style else "")
            + "其余图片如有，用于参考业务指定的人物气质、服饰和场景。"
            "不得复制参考图中的具体人物身份、物体摆放或构图。"
        )
    parts.append(f"画面比例：{radio}。像素不必正好是 {size}，程序会缩放到 {size}。")
    return "\n\n".join(parts)


def _hash_file(path: Path) -> str:
    digest = hashlib.sha256()
    with path.open("rb") as source:
        for chunk in iter(lambda: source.read(1024 * 1024), b""):
            digest.update(chunk)
    return digest.hexdigest()


def _cache_signature(prompt: str, reference_paths: list[Path], radio: str, size: str) -> str:
    payload = {
        "version": AGENT_IMAGE_TASK_VERSION,
        "prompt": prompt,
        "reference_sha256": [_hash_file(path) for path in reference_paths],
        "radio": radio,
        "size": size,
    }
    encoded = json.dumps(payload, ensure_ascii=False, sort_keys=True, separators=(",", ":")).encode("utf-8")
    return hashlib.sha256(encoded).hexdigest()


def _write_cache_metadata(path: Path, cache_signature: str) -> None:
    metadata_path = path.with_suffix(".json")
    temporary = metadata_path.with_name(f".{metadata_path.stem}-{uuid4().hex}.tmp.json")
    temporary.write_text(
        json.dumps({"cache_signature": cache_signature}, ensure_ascii=False, sort_keys=True),
        encoding="utf-8",
    )
    temporary.replace(metadata_path)


def _validate_task(task: dict, seen: set[str]) -> tuple[str, str, str]:
    if not isinstance(task, dict):
        raise AgentImageTaskError("每个生图任务都必须是对象")
    image_id = str(task.get("image_id") or "").strip()
    prompt = str(task.get("prompt") or "").strip()
    kind = str(task.get("kind") or "image").strip()
    if not image_id or not re.fullmatch(r"[A-Za-z0-9_-]+", image_id):
        raise AgentImageTaskError(
            "image_id 只能包含英文字母、数字、下划线和连字符",
            {"image_id": image_id},
        )
    if image_id in seen:
        raise AgentImageTaskError(f"image_id 重复：{image_id}")
    if not prompt:
        raise AgentImageTaskError(f"生图任务 {image_id} 的 prompt 不能为空")
    seen.add(image_id)
    return image_id, prompt, kind


def prepare_agent_image_tasks(
    tasks: list[dict],
    style: str | None,
    radio: str,
    size: str,
    cache_dir: str | Path,
    *,
    additional_reference_image_paths: list[str | Path] | None = None,
    context_path: str | Path | None = None,
    force_image_ids: list[str] | None = None,
    force_images: bool = False,
    metadata: dict | None = None,
) -> dict:
    """生成与具体工作流无关的宿主 Agent 生图任务和缓存状态。"""
    if not isinstance(tasks, list) or not tasks:
        raise InvalidParameterError("tasks", "tasks 必须是非空生图任务列表")
    if not isinstance(force_images, bool):
        raise InvalidParameterError("force_images", "force_images 必须是布尔值")
    width, height, normalized_radio, normalized_size = _validate_dimensions(radio, size)
    style_name = str(style or "").strip()
    selected_style = _select_style(style_name) if style_name else None
    if additional_reference_image_paths is not None and not isinstance(additional_reference_image_paths, list):
        raise InvalidParameterError(
            "additional_reference_image_paths",
            "additional_reference_image_paths 必须是参考图路径数组或不传",
        )
    reference_paths: list[Path] = []
    if selected_style:
        reference_path = Path(selected_style["reference_image_path"]).resolve()
        if not reference_path.is_file():
            raise ReferenceImageError(f"风格参考图不存在：{reference_path}")
        reference_paths.append(reference_path)
    for value in additional_reference_image_paths or []:
        extra_path = Path(str(value)).resolve()
        if not extra_path.is_file():
            raise ReferenceImageError(f"附加参考图不存在：{extra_path}")
        if extra_path not in reference_paths:
            reference_paths.append(extra_path)
    output_root = Path(cache_dir).resolve()
    output_root.mkdir(parents=True, exist_ok=True)
    normalized: list[tuple[str, str, str]] = []
    seen: set[str] = set()
    for task in tasks:
        normalized.append(_validate_task(task, seen))
    forced = set(force_image_ids or [])
    unknown = forced.difference(seen)
    if unknown:
        raise AgentImageTaskError(
            f"要重做的图片不存在：{sorted(unknown)}",
            {"supported_image_ids": sorted(seen)},
        )
    prepared: list[dict] = []
    for image_id, prompt, kind in normalized:
        task_reference_paths = list(reference_paths)
        output_path = output_root / f"{image_id}.png"
        has_references = bool(task_reference_paths)
        final_prompt = _final_prompt(
            prompt,
            selected_style,
            normalized_radio,
            normalized_size,
            has_references=has_references,
        )
        cache_signature = _cache_signature(
            final_prompt,
            task_reference_paths,
            normalized_radio,
            normalized_size,
        )
        cache_hit = (
            _valid_image(output_path, width, height, cache_signature)
            and not force_images
            and image_id not in forced
        )
        prepared.append(
            {
                "image_id": image_id,
                "kind": kind,
                "prompt": final_prompt,
                "style": selected_style["id"] if selected_style else None,
                "radio": normalized_radio,
                "size": normalized_size,
                "referenced_image_paths": [_agent_path(path) for path in task_reference_paths],
                "reference_images_required": has_references,
                "reference_failure_policy": (
                    "必须把 referenced_image_paths 作为本地图片数组原样传给当前生图能力；"
                    "若宿主不能传本地参考图，按 capability_unavailable=true 提交失败，"
                    "禁止用文字描述、提示词复述或想象参考图替代。"
                    if has_references
                    else "本任务没有参考图，不要附加画风或其它参考图。"
                ),
                "output_path": _agent_path(output_path),
                "cache_signature": cache_signature,
                "cache_hit": cache_hit,
                "needs_generation": not cache_hit,
            }
        )
    resolved_context = Path(context_path or output_root / AGENT_IMAGE_CONTEXT_NAME).resolve()
    context = {
        "version": AGENT_IMAGE_TASK_VERSION,
        "status": "awaiting_agent_images",
        "tasks": prepared,
        "metadata": dict(metadata or {}),
        "context_path": _agent_path(resolved_context),
    }
    resolved_context.parent.mkdir(parents=True, exist_ok=True)
    resolved_context.write_text(json.dumps(context, ensure_ascii=False, indent=2), encoding="utf-8")
    return context


def _load_image_context(context_path: str | Path) -> tuple[Path, dict, list[dict], dict[str, dict]]:
    resolved_context = Path(context_path).resolve()
    if not resolved_context.is_file():
        raise AgentImageTaskError(f"生图任务上下文不存在：{resolved_context}")
    try:
        context = json.loads(resolved_context.read_text(encoding="utf-8"))
    except (OSError, json.JSONDecodeError) as exc:
        raise AgentImageTaskError(f"读取生图任务上下文失败：{resolved_context}。{exc}") from exc
    tasks = context.get("tasks")
    if not isinstance(tasks, list) or not tasks:
        raise AgentImageTaskError("生图任务上下文缺少 tasks")
    return resolved_context, context, tasks, {str(task["image_id"]): task for task in tasks}


def _parse_image_results(images: list[dict], *, allow_empty: bool) -> dict[str, Path]:
    if not isinstance(images, list):
        raise InvalidParameterError("images", "images 必须是图片结果列表")
    if not images and not allow_empty:
        raise InvalidParameterError("images", "images 必须是非空图片结果列表")
    provided: dict[str, Path] = {}
    for item in images:
        if not isinstance(item, dict) or not str(item.get("image_id") or "").strip() or not str(item.get("image_path") or "").strip():
            raise AgentImageTaskError("每个图片结果都必须包含 image_id 和 image_path")
        image_id = str(item["image_id"]).strip()
        if image_id in provided:
            raise AgentImageTaskError(f"图片结果重复：{image_id}")
        provided[image_id] = Path(str(item["image_path"])).resolve()
    return provided


def _task_is_cached(task: dict) -> bool:
    width, height, _, _ = _validate_dimensions(str(task["radio"]), str(task["size"]))
    return _valid_image(
        Path(task["output_path"]).resolve(),
        width,
        height,
        str(task.get("cache_signature") or "") or None,
    )


def _cache_status(tasks: list[dict]) -> tuple[list[str], list[str]]:
    cached: list[str] = []
    pending: list[str] = []
    for task in tasks:
        image_id = str(task["image_id"])
        if _task_is_cached(task):
            cached.append(image_id)
        else:
            pending.append(image_id)
    return cached, pending


def _persist_provided_images(
    task_by_id: dict[str, dict],
    provided: dict[str, Path],
) -> list[str]:
    unknown = set(provided).difference(task_by_id)
    if unknown:
        raise AgentImageTaskError(
            f"提交了未知图片：{sorted(unknown)}",
            {"supported_image_ids": sorted(task_by_id)},
        )
    saved: list[str] = []
    for image_id, source_path in provided.items():
        task = task_by_id[image_id]
        width, height, _, _ = _validate_dimensions(str(task["radio"]), str(task["size"]))
        target = Path(task["output_path"]).resolve()
        _save_checked_image(source_path, target, image_id, width, height)
        if task.get("cache_signature"):
            _write_cache_metadata(target, str(task["cache_signature"]))
        saved.append(image_id)
    return saved


def _save_checked_image(
    source_path: Path,
    output_path: Path,
    image_id: str,
    width: int,
    height: int,
) -> None:
    if not source_path.is_file():
        raise AgentImageTaskError(
            f"当前 Agent 生成的图片不存在：{source_path}",
            {"image_id": image_id, "image_path": str(source_path)},
        )
    try:
        with Image.open(source_path) as image:
            image.load()
            fitted = _fit_image(image, width, height)
            _write_png(fitted.copy(), output_path)
    except AgentImageTaskError:
        raise
    except (OSError, ValueError) as exc:
        raise AgentImageTaskError(
            f"图片 {image_id} 不是有效图片：{source_path}",
            {"image_id": image_id, "image_path": str(source_path)},
        ) from exc


def save_agent_image_tasks(context_path: str | Path, images: list[dict]) -> dict:
    """把已生成的图片立即写入工作流缓存；未齐的任务下次 prepare 会继续命中已缓存项。"""
    resolved_context, context, tasks, task_by_id = _load_image_context(context_path)
    provided = _parse_image_results(images, allow_empty=False)
    saved = _persist_provided_images(task_by_id, provided)
    cached, pending = _cache_status(tasks)
    return {
        "status": "cached" if not pending else "partial",
        "saved_image_ids": saved,
        "cached_image_ids": cached,
        "pending_image_ids": pending,
        "context_path": str(resolved_context),
    }


def submit_agent_image_tasks(
    context_path: str | Path,
    images: list[dict],
    *,
    manifest_path: str | Path | None = None,
) -> dict:
    """接收已缓存的宿主 Agent 图片并写出清单；不调用千问。"""
    resolved_context, context, tasks, task_by_id = _load_image_context(context_path)
    provided = _parse_image_results(images, allow_empty=True)
    if provided:
        _persist_provided_images(task_by_id, provided)
    providers: dict[str, str] = {}
    for image_id, task in task_by_id.items():
        width, height, _, _ = _validate_dimensions(str(task["radio"]), str(task["size"]))
        target = Path(task["output_path"]).resolve()
        if image_id in provided:
            providers[image_id] = "current_agent"
        elif not _valid_image(
            target,
            width,
            height,
            str(task.get("cache_signature") or "") or None,
        ):
            cached, pending = _cache_status(tasks)
            raise AgentImageTaskError(
                f"缺少图片 {image_id}；已缓存 {cached}，仍缺 {pending}。请先把已生成的图写入缓存后再提交",
                {
                    "image_id": image_id,
                    "expected_output_path": str(target),
                    "cached_image_ids": cached,
                    "pending_image_ids": pending,
                },
            )
        else:
            providers[image_id] = str(task.get("provider") or "cache")
    resolved_manifest = Path(manifest_path or resolved_context.parent / AGENT_IMAGE_MANIFEST_NAME).resolve()
    manifest = {
        "version": AGENT_IMAGE_TASK_VERSION,
        "status": "ready",
        "images": {image_id: str(Path(task["output_path"]).resolve()) for image_id, task in task_by_id.items()},
        "providers": providers,
        "metadata": dict(context.get("metadata") or {}),
        "manifest_path": str(resolved_manifest),
    }
    resolved_manifest.parent.mkdir(parents=True, exist_ok=True)
    resolved_manifest.write_text(json.dumps(manifest, ensure_ascii=False, indent=2), encoding="utf-8")
    return manifest
