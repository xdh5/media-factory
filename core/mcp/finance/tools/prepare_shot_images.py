"""按 Skill 指定的 image_config 准备镜头图任务。"""

from __future__ import annotations

import hashlib
import json
from pathlib import Path

from core.tools.generate_image import ImageGenerationError, list_local_images

from .._constants import (
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


def _image_config(config: dict) -> tuple[str, str]:
    if not isinstance(config, dict):
        raise WorkflowStepError("image_config 必须是对象")
    source = str(config.get("source") or "").strip()
    if source == "local_library":
        library_line = str(config.get("library_line") or "").strip()
        if not library_line:
            raise WorkflowStepError("image_config.library_line 不能为空（local_library 时必填）")
        return source, library_line
    raise WorkflowStepError(
        f"不支持的 image_config.source：{source or '(空)'}；当前仅支持 local_library",
        {"supported_sources": ["local_library"]},
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
            "对照每个镜头的 match_query 与 library_catalog 中各图的 caption，"
            "为每个 image_id 选出语义最贴近的一张图；"
            "然后调用 finance_submit_images，"
            "images 传入 [{image_id, image_path}]，image_path 使用 catalog 中的路径。"
            "同一期可重复使用同一张图，无需考虑历史选用均分。"
        ),
    }
    context_path.write_text(json.dumps(context, ensure_ascii=False, indent=2), encoding="utf-8")
    return {
        **context,
        "image_source": "local",
        "library_line": library_line,
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
    source, library_line = _image_config(image_config)
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
        return _prepare_local_library(shots, cache_root, metadata, library_line)
    raise WorkflowStepError(f"未实现的 image_config.source：{source}")
