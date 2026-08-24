"""按 Skill 指定的 image_config 准备镜头图任务。"""

from __future__ import annotations

import hashlib
import json
from pathlib import Path

from core.tools.generate_image import ImageGenerationError, list_local_images, prepare_agent_image_tasks

from .._constants import (
    GENERATED_IMAGE_LIBRARY_ROOT,
    MCP_ID,
    STORYBOARD_CONTEXT_FILE_NAME,
    STORYBOARD_TEXT_FILE_NAME,
    VIDEO_RADIO,
    VIDEO_SIZE,
)
from .._errors import WorkflowStepError
from .narration import display_subtitle_text
from .save_draft import load_draft
from .storyboard import parse_storyboard


def _image_config(config: dict) -> dict:
    if not isinstance(config, dict):
        raise WorkflowStepError("image_config 必须是对象")
    source = str(config.get("source") or "").strip()
    if source == "local_library":
        library_line = str(config.get("library_line") or "").strip()
        if not library_line:
            raise WorkflowStepError("image_config.library_line 不能为空（local_library 时必填）")
        return {"source": source, "library_line": library_line}
    if source == "qwen_reference":
        reference_image_path = str(config.get("reference_image_path") or "").strip()
        if not reference_image_path:
            raise WorkflowStepError("image_config.reference_image_path 不能为空（qwen_reference 时必填）")
        return {"source": source, "reference_image_path": reference_image_path}
    raise WorkflowStepError(
        f"不支持的 image_config.source：{source or '(空)'}",
        {"supported_sources": ["local_library", "qwen_reference"]},
    )


def _prepare_local_library(
    shots: list[dict],
    cache_root: Path,
    metadata: dict,
    library_line: str,
) -> dict:
    try:
        catalog = list_local_images(library_line)
    except ImageGenerationError as extra:
        raise WorkflowStepError(extra.message, extra.details) from extra
    output_root = cache_root / "agent-images"
    output_root.mkdir(parents=True, exist_ok=True)
    tasks = []
    selection_tasks = []
    for shot in shots:
        subtitle = display_subtitle_text(str(shot.get("subtitle") or ""))
        prompt = str(shot["prompt"])
        selection_tasks.append(
            {
                "image_id": shot["id"],
                "subtitle": subtitle,
                "prompt": prompt,
                "match_query": f"{subtitle}\n{prompt}".strip(),
            }
        )
        tasks.append(
            {
                "image_id": shot["id"],
                "kind": "shot",
                "prompt": prompt,
                "style": None,
                "radio": VIDEO_RADIO,
                "size": VIDEO_SIZE,
                "referenced_image_paths": [],
                "reference_images_required": False,
                "output_path": str((output_root / f"{shot['id']}.png").resolve()),
                "cache_signature": None,
                "cache_hit": False,
                "needs_generation": False,
                "provider": "local_library",
            }
        )
    metadata = {
        **metadata,
        "image_source": "local",
        "library_line": library_line,
        "library_catalog": catalog,
    }
    context_path = output_root / "agent-image-context.json"
    context = {
        "version": 4,
        "status": "awaiting_library_selection",
        "tasks": tasks,
        "metadata": metadata,
        "context_path": context_path.resolve().as_posix(),
        "library_catalog": catalog,
        "selection_tasks": selection_tasks,
        "selection_instructions": (
            f"本期已固定使用图库 line={library_line}，所有镜头必须且只能来自该图库。"
            "对照每个镜头的 match_query 与 library_catalog 中各图的 caption，"
            "为每个 image_id 选出语义最贴近的一张图；"
            "然后调用 finance_submit_images，"
            "images 传入 [{image_id, image_path}]，image_path 使用 catalog 中的路径。"
            "同一期可重复使用同一张图，禁止混用另一个图库。"
        ),
    }
    context_path.write_text(json.dumps(context, ensure_ascii=False, indent=2), encoding="utf-8")
    return {
        **context,
        "image_source": "local",
        "library_line": library_line,
    }


def _prepare_qwen_reference(
    shots: list[dict],
    cache_root: Path,
    metadata: dict,
    reference_image_path: str,
    run_id: str,
) -> dict:
    GENERATED_IMAGE_LIBRARY_ROOT.mkdir(parents=True, exist_ok=True)
    existing_ids = []
    for image_path in GENERATED_IMAGE_LIBRARY_ROOT.glob("*.png"):
        if image_path.stem.isdigit() and int(image_path.stem) > 0:
            existing_ids.append(int(image_path.stem))
    first_library_id = max(existing_ids, default=0) + 1
    tasks = []
    captions = {}
    library_ids = {}
    for offset, shot in enumerate(shots):
        prompt = str(shot["prompt"]).strip()
        image_id = str(shot["id"])
        library_id = first_library_id + offset
        captions[image_id] = prompt
        library_ids[image_id] = library_id
        tasks.append(
            {
                "image_id": image_id,
                "kind": "shot",
                "prompt": (
                    f"{prompt}\n\n"
                    "画风硬性要求：明亮、通透、温暖的轻油画风，可见自然细腻的油画笔触，"
                    "使用高亮自然光、浅色背景与清爽配色，不得阴暗、压抑、厚重或脏灰。"
                    "人物硬性要求：必须以人像为明确主体，画面中的所有人物都必须是欧美人，"
                    "具有自然真实的欧美面孔。人物姿态挺拔舒展，神态坚定从容，"
                    "呈现有力量、正能量、自信、积极向上的气质，不得软弱、颓丧、焦虑或消沉。"
                    "参考图仅用于参考轻油画风格、笔触、光影、色彩和画面质感。"
                    "禁止参考或复制图中的人物身份、面孔、发型、服装、办公室场景、构图、书桌、"
                    "电脑及其他物体摆放。必须优先执行当前镜头的场景描述，不得默认生成蓝色西装、"
                    "办公桌、笔记本电脑或窗边办公室。画面中禁止出现文字、字母、Logo 和水印。"
                ),
            }
        )
    output_root = GENERATED_IMAGE_LIBRARY_ROOT
    context_path = cache_root / "qwen-images" / "agent-image-context.json"
    try:
        context = prepare_agent_image_tasks(
            tasks,
            None,
            VIDEO_RADIO,
            VIDEO_SIZE,
            output_root,
            additional_reference_image_paths=[reference_image_path],
            context_path=context_path,
            metadata={
                **metadata,
                "image_source": "qwen_reference",
                "run_id": run_id,
                "generated_image_dir": str(output_root.resolve()),
                "caption_by_image_id": captions,
                "library_id_by_image_id": library_ids,
            },
            reference_usage="style_only",
        )
    except ImageGenerationError as extra:
        raise WorkflowStepError(extra.message, extra.details) from extra
    if len(context["tasks"]) != len(shots):
        raise WorkflowStepError("千问生图任务没有完整覆盖全部镜头")
    context["status"] = "awaiting_qwen_generation"
    for task in context["tasks"]:
        task["provider"] = "dashscope"
        task["output_path"] = str(
            (output_root / f"{library_ids[str(task['image_id'])]}.png").resolve()
        ).replace("\\", "/")
    Path(context["context_path"]).write_text(
        json.dumps(context, ensure_ascii=False, indent=2),
        encoding="utf-8",
    )
    return {
        **context,
        "image_source": "qwen_reference",
        "generated_image_dir": str(output_root.resolve()),
        "generation_task_count": len(context["tasks"]),
        "next_tool": "finance_start_generate_images",
    }


def prepare_shot_images(
    draft_path: str | Path,
    storyboard_text: str,
    *,
    image_config: dict,
) -> dict:
    normalized_storyboard = str(storyboard_text or "").strip()
    if not normalized_storyboard:
        raise WorkflowStepError("storyboard_text 不能为空")
    normalized_config = _image_config(image_config)
    source = normalized_config["source"]
    resolved_draft, draft = load_draft(draft_path, "财经稿件")
    if not draft.get("title") or not str(draft.get("cache_dir") or "").strip():
        raise WorkflowStepError("财经稿件缺少 title 或 cache_dir")
    cache_root = Path(draft["cache_dir"]).resolve()
    _, storyboard_context = load_draft(cache_root / STORYBOARD_CONTEXT_FILE_NAME, "分镜上下文")
    timeline = storyboard_context.get("timeline")
    if not isinstance(timeline, list) or not timeline:
        raise WorkflowStepError("分镜上下文缺少有效 timeline，请先完成 finance_prepare_storyboard")
    shots = parse_storyboard(normalized_storyboard, timeline)
    storyboard_path = cache_root / STORYBOARD_TEXT_FILE_NAME
    storyboard_path.write_text(normalized_storyboard, encoding="utf-8")
    metadata = {
        "workflow": MCP_ID,
        "line": MCP_ID,
        "draft_path": str(resolved_draft),
        "storyboard_text": normalized_storyboard,
        "storyboard_path": str(storyboard_path),
        "storyboard_sha256": hashlib.sha256(normalized_storyboard.encode("utf-8")).hexdigest(),
        "image_config": image_config,
        "tts_path": storyboard_context.get("tts_path"),
    }
    if source == "local_library":
        return _prepare_local_library(shots, cache_root, metadata, normalized_config["library_line"])
    if source == "qwen_reference":
        return _prepare_qwen_reference(
            shots,
            cache_root,
            metadata,
            normalized_config["reference_image_path"],
            str(draft["run_id"]),
        )
    raise WorkflowStepError(f"未实现的 image_config.source：{source}")
