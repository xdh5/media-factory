"""定位、裁切并验收透明主体，维护切图缓存。"""

import hashlib
import json
from collections import deque
from pathlib import Path

from PIL import Image, ImageChops, ImageOps

from ..config import (
    CARD_GRID_COLUMNS,
    SUBJECT_ALPHA_THRESHOLD,
    SUBJECT_COMPONENT_MIN_RATIO,
    SUBJECT_CUTOUT_STRATEGY_VERSION,
    SUBJECT_GENERATION_MAX_ATTEMPTS,
    SUBJECT_SHEET_SIZE,
    WORDS_PER_TASK,
)
from ..errors import CardCompositionError

def _fit_sheet(image: Image.Image) -> Image.Image:
    """缩放到主体图尺寸。比例一致时只缩放，不一致时居中裁切，不报尺寸错误。"""
    width, height = SUBJECT_SHEET_SIZE
    if image.size == (width, height):
        return image
    expected = round(image.width * height / width)
    if abs(image.height - expected) <= 1:
        return image.resize((width, height), Image.Resampling.LANCZOS)
    return ImageOps.fit(image, (width, height), method=Image.Resampling.LANCZOS)


def _sheet(path: Path) -> Image.Image:
    try:
        with Image.open(path) as source:
            image = ImageOps.exif_transpose(source).convert("RGBA")
    except Exception as extra:
        raise CardCompositionError("上传的文件不是有效的主体素材图") from extra
    return _fit_sheet(image)


def _visible_mask(image: Image.Image) -> Image.Image:
    return image.getchannel("A").point(lambda value: 255 if value > SUBJECT_ALPHA_THRESHOLD else 0)


def _remove_tiny_islands(image: Image.Image) -> Image.Image:
    """删除误带入相邻格的极小孤立透明前景，保留正常的多人物动作主体。"""
    mask = _visible_mask(image)
    width, height = mask.size
    pixels = mask.load()
    seen: set[tuple[int, int]] = set()
    components: list[list[tuple[int, int]]] = []
    for y in range(height):
        for x in range(width):
            if pixels[x, y] == 0 or (x, y) in seen:
                continue
            queue = deque([(x, y)])
            seen.add((x, y))
            component: list[tuple[int, int]] = []
            while queue:
                current_x, current_y = queue.popleft()
                component.append((current_x, current_y))
                for next_x, next_y in (
                    (current_x - 1, current_y),
                    (current_x + 1, current_y),
                    (current_x, current_y - 1),
                    (current_x, current_y + 1),
                ):
                    if (
                        0 <= next_x < width
                        and 0 <= next_y < height
                        and pixels[next_x, next_y] != 0
                        and (next_x, next_y) not in seen
                    ):
                        seen.add((next_x, next_y))
                        queue.append((next_x, next_y))
            components.append(component)
    if len(components) < 2:
        return image
    largest = max(len(component) for component in components)
    minimum = max(1, round(largest * SUBJECT_COMPONENT_MIN_RATIO))
    retained = Image.new("L", image.size, 0)
    retained_pixels = retained.load()
    edge_limit = round(width * 0.2)
    for component in components:
        component_width = max(x for x, _ in component) + 1
        is_left_edge_collision = (
            len(component) < round(largest * 0.2)
            and min(x for x, _ in component) == 0
            and component_width <= edge_limit
        )
        if len(component) < minimum or is_left_edge_collision:
            continue
        for x, y in component:
            retained_pixels[x, y] = 255
    alpha = image.getchannel("A")
    alpha = ImageChops.multiply(alpha, retained)
    result = image.copy()
    result.putalpha(alpha)
    return result


def _sheet_signature(path: Path) -> str:
    digest = hashlib.sha256()
    digest.update(SUBJECT_CUTOUT_STRATEGY_VERSION.encode("utf-8"))
    digest.update(b"\0")
    digest.update(path.read_bytes())
    return digest.hexdigest()


def _cutout_cache_paths(cache_dir: Path) -> tuple[Path, list[Path]]:
    return cache_dir / "signature.txt", [cache_dir / f"{index:02d}.png" for index in range(1, WORDS_PER_TASK + 1)]


def _inspection_paths(cache_dir: Path) -> tuple[Path, Path]:
    return cache_dir / "inspection.json", cache_dir / "review-history.json"


def _cutout_review_sheet_path(cache_dir: Path) -> Path:
    """返回十张切图的整体验收图路径。"""
    return cache_dir / "subject-cutouts-review.png"


def _load_cached_cutouts(cache_dir: Path, signature: str) -> list[Image.Image] | None:
    marker, paths = _cutout_cache_paths(cache_dir)
    if not marker.is_file() or marker.read_text(encoding="utf-8").strip() != signature:
        return None
    inspection_path, _ = _inspection_paths(cache_dir)
    try:
        inspection = json.loads(inspection_path.read_text(encoding="utf-8"))
    except (OSError, json.JSONDecodeError):
        return None
    if inspection.get("signature") != signature or inspection.get("approved") is not True:
        return None
    images: list[Image.Image] = []
    for path in paths:
        if not path.is_file():
            return None
        try:
            with Image.open(path) as source:
                image = source.convert("RGBA")
        except Exception:
            return None
        if _visible_mask(image).getbbox() is None:
            return None
        images.append(image)
    return images


def _save_cached_cutouts(cache_dir: Path, signature: str, subjects: list[Image.Image]) -> None:
    cache_dir.mkdir(parents=True, exist_ok=True)
    marker, paths = _cutout_cache_paths(cache_dir)
    inspection_path, history_path = _inspection_paths(cache_dir)
    for path, subject in zip(paths, subjects):
        subject.save(path, format="PNG")
    marker.write_text(signature, encoding="utf-8")
    inspection_path.unlink(missing_ok=True)
    try:
        history = json.loads(history_path.read_text(encoding="utf-8"))
    except (OSError, json.JSONDecodeError):
        history = {}
    if history.get("signature") != signature:
        history_path.write_text(
            json.dumps({"signature": signature, "failed_rounds": 0}, ensure_ascii=False, indent=2),
            encoding="utf-8",
        )


SHEET_FAILURE_KINDS = frozenset({
    "background_edge",
    "text",
    "watermark",
    "style",
    "count",
    "completeness",
})


def review_subject_sheet(
    subject_sheet_path: str | Path,
    cutout_cache_dir: str | Path,
    review: dict,
) -> dict:
    """记录十张透明切图的视觉验收结论，未通过时禁止拼卡。"""
    sheet_path = Path(subject_sheet_path).resolve()
    cache_dir = Path(cutout_cache_dir).resolve()
    signature = _sheet_signature(sheet_path)
    marker, cutout_paths = _cutout_cache_paths(cache_dir)
    if not marker.is_file() or marker.read_text(encoding="utf-8").strip() != signature:
        raise CardCompositionError("当前主体图没有可检查的透明切图缓存，请先调用主体图验收")
    review_sheet_path = _cutout_review_sheet_path(cache_dir)
    if not review_sheet_path.is_file():
        raise CardCompositionError("十张切图的整体验收图不存在，请先调用主体图验收")
    if not isinstance(review, dict):
        raise CardCompositionError("整图验收结果必须是对象")
    valid = review.get("valid")
    if not isinstance(valid, bool):
        raise CardCompositionError("review.valid 必须是布尔值")
    failure_kind = str(review.get("failure_kind") or "").strip().casefold()
    issue = str(review.get("issue") or "").strip()
    if valid:
        failure_kind = ""
    elif failure_kind not in SHEET_FAILURE_KINDS:
        raise CardCompositionError(
            f"验收失败时 failure_kind 必须是 {sorted(SHEET_FAILURE_KINDS)} 之一"
        )
    elif not issue:
        raise CardCompositionError("验收失败时 issue 必须说明具体问题")
    normalized = {
        "valid": valid,
        "failure_kind": failure_kind,
        "issue": issue,
        "subject_count": review.get("subject_count"),
    }
    if any(not path.is_file() for path in cutout_paths):
        raise CardCompositionError("十张透明切图缓存不完整，请重新执行主体图验收")
    inspection_path, history_path = _inspection_paths(cache_dir)
    if valid:
        inspection_path.write_text(
            json.dumps({"signature": signature, "approved": True, "review": normalized}, ensure_ascii=False, indent=2),
            encoding="utf-8",
        )
        return {
            "approved": True,
            "review": normalized,
            "cutout_review_sheet_path": str(review_sheet_path),
            "cutout_paths": [str(path) for path in cutout_paths],
            "next_tool": "language_learning_start_compose_cards",
        }
    try:
        history = json.loads(history_path.read_text(encoding="utf-8"))
    except (OSError, json.JSONDecodeError):
        history = {"signature": signature, "failed_rounds": 0}
    failed_rounds = int(history.get("failed_rounds") or 0) + 1
    history_path.write_text(
        json.dumps({"signature": signature, "failed_rounds": failed_rounds}, ensure_ascii=False, indent=2),
        encoding="utf-8",
    )
    validation_issues = [f"[{failure_kind}] {issue}" if failure_kind else issue]
    action = "relocalize" if failure_kind == "completeness" else "regenerate"
    correction_instruction = (
        "重新定位主体并提交更保守的边界框，确保主体结构完整且不带入相邻主体"
        if action == "relocalize"
        else "重新生成带真实 Alpha 通道的透明 PNG，并修正验收指出的问题"
    )
    return {
        "approved": False,
        "review": normalized,
        "failed_rounds": failed_rounds,
        "action": action,
        "validation_issues": validation_issues,
        "correction_instruction": correction_instruction,
        "next_tool": (
            "language_learning_validate_subject_sheet"
            if action == "relocalize"
            else "language_learning_prepare_images"
        ),
    }


def approved_subject_cutout_paths(
    subject_sheet_path: str | Path,
    cutout_cache_dir: str | Path,
) -> list[str]:
    """返回已通过整图验收的十张透明主体图路径。"""
    sheet_path = Path(subject_sheet_path).resolve()
    cache_dir = Path(cutout_cache_dir).resolve()
    signature = _sheet_signature(sheet_path)
    if _load_cached_cutouts(cache_dir, signature) is None:
        raise CardCompositionError("预制词包主题图尚未完成切图和整图验收，不能提交词包")
    _, paths = _cutout_cache_paths(cache_dir)
    return [str(path.resolve()) for path in paths]


def require_transparent_subject_sheet(subject_sheet_path: str | Path) -> None:
    """确保预制词包原始主题图带有真实透明像素。"""
    sheet_path = Path(subject_sheet_path).resolve()
    sheet = _sheet(sheet_path)
    alpha = sheet.getchannel("A")
    histogram = alpha.histogram()
    transparent_pixels = sum(histogram[: SUBJECT_ALPHA_THRESHOLD + 1])
    transparent_ratio = transparent_pixels / (sheet.width * sheet.height)
    if transparent_ratio < 0.05:
        raise CardCompositionError(
            "主体图必须带真实 Alpha 透明背景，且透明背景面积不能少于画布的 5%；"
            "当前图片不符合要求，不能继续切图"
        )


def _validated_visual_layout(payload: dict) -> dict:
    """只校验宿主 Agent 提交的十个定位框，不做内容质量判断。"""
    if not isinstance(payload, dict):
        raise CardCompositionError("宿主 Agent 的主体定位结果必须是对象")
    raw_boxes = payload.get("boxes")
    boxes: list[list[int]] = []
    issues: list[str] = []
    if not isinstance(raw_boxes, list):
        issues.append("宿主 Agent 没有返回主体边界框列表")
    else:
        if len(raw_boxes) != WORDS_PER_TASK:
            issues.append(
                f"宿主 Agent 返回 {len(raw_boxes)} 个主体边界框，必须为 {WORDS_PER_TASK} 个"
            )
        for index, raw_box in enumerate(raw_boxes, 1):
            if not isinstance(raw_box, list) or len(raw_box) != 4:
                issues.append(f"宿主 Agent 返回的第 {index} 个边界框格式不正确")
                continue
            try:
                box = [max(0, min(1000, int(value))) for value in raw_box]
            except (TypeError, ValueError):
                issues.append(f"宿主 Agent 返回的第 {index} 个边界框坐标不是整数")
                continue
            if box[2] <= box[0] or box[3] <= box[1]:
                issues.append(f"宿主 Agent 返回的第 {index} 个边界框范围无效")
                continue
            boxes.append(box)
    return {
        "valid": not issues,
        "object_count": WORDS_PER_TASK,
        "top_count": CARD_GRID_COLUMNS,
        "bottom_count": CARD_GRID_COLUMNS,
        "has_text": False,
        "reason": str(payload.get("reason") or "").strip(),
        "boxes": boxes,
        "issues": issues,
        "source": "host_agent",
    }


def _detect_subjects(
    sheet: Image.Image,
    visual_boxes: list[list[int]],
) -> tuple[list[Image.Image], list[dict], list[str], list[list[int]]]:
    """按宿主 Agent 给出的定位框裁出十张透明主体图。"""
    issues: list[str] = []
    subjects: list[Image.Image] = []
    cells: list[dict] = []
    crop_boxes = visual_boxes
    for index, crop_box in enumerate(crop_boxes, 1):
        box = (
            crop_box[0] * sheet.width // 1000,
            crop_box[1] * sheet.height // 1000,
            max(1, crop_box[2] * sheet.width // 1000),
            max(1, crop_box[3] * sheet.height // 1000),
        )
        region = sheet.crop(box)
        local_bbox = _visible_mask(region).getbbox()
        if local_bbox is None:
            issue = f"第 {index} 个位置没有有效透明前景"
            issues.append(issue)
            cells.append({
                "index": index,
                "valid": False,
                "bbox": None,
                "foreground_ratio": 0.0,
                "issues": [issue],
            })
            continue
        initial_bbox = local_bbox
        subject_region = _remove_tiny_islands(region.crop(initial_bbox))
        final_bbox = _visible_mask(subject_region).getbbox()
        if final_bbox is None:
            issue = f"第 {index} 个位置去除孤立残片后没有有效前景"
            issues.append(issue)
            continue
        bbox = (
            box[0] + initial_bbox[0] + final_bbox[0],
            box[1] + initial_bbox[1] + final_bbox[1],
            box[0] + initial_bbox[0] + final_bbox[2],
            box[1] + initial_bbox[1] + final_bbox[3],
        )
        subject = subject_region.crop(final_bbox)
        subjects.append(subject)
        foreground_pixels = _visible_mask(subject).histogram()[255]
        cells.append({
            "index": index,
            "valid": True,
            "bbox": list(bbox),
            "foreground_ratio": round(foreground_pixels / (sheet.width * sheet.height), 4),
            "issues": [],
        })
    if issues:
        for cell in cells:
            cell["valid"] = False
    return subjects, cells, issues, crop_boxes


def _build_cutout_review_sheet(subjects: list[Image.Image]) -> Image.Image:
    """把十张实际切图排成透明验收图，供 LLM 检查是否切坏。"""
    canvas = Image.new("RGBA", SUBJECT_SHEET_SIZE, (0, 0, 0, 0))
    cell_width = SUBJECT_SHEET_SIZE[0] // CARD_GRID_COLUMNS
    cell_height = SUBJECT_SHEET_SIZE[1] // 2
    padding = 24
    for index, subject in enumerate(subjects):
        scale = min(
            (cell_width - padding * 2) / subject.width,
            (cell_height - padding * 2) / subject.height,
        )
        width = max(1, round(subject.width * scale))
        height = max(1, round(subject.height * scale))
        fitted = subject.resize((width, height), Image.Resampling.LANCZOS)
        column = index % CARD_GRID_COLUMNS
        row = index // CARD_GRID_COLUMNS
        left = column * cell_width + (cell_width - width) // 2
        top = row * cell_height + (cell_height - height) // 2
        canvas.alpha_composite(fitted, (left, top))
    return canvas


def validate_subject_sheet(
    subject_sheet_path: str | Path,
    visual_layout: dict,
    cutout_cache_dir: str | Path | None = None,
) -> dict:
    """校验真实透明主题图，并按宿主 Agent 的定位结果裁切。"""
    sheet_path = Path(subject_sheet_path).resolve()
    require_transparent_subject_sheet(sheet_path)
    sheet = _sheet(sheet_path)
    vision = _validated_visual_layout(visual_layout)
    issues = list(vision["issues"])
    subjects: list[Image.Image] = []
    cells: list[dict] = []
    crop_boxes: list[list[int]] = []
    if not issues:
        subjects, cells, crop_issues, crop_boxes = _detect_subjects(
            sheet,
            vision["boxes"],
        )
        issues.extend(crop_issues)
    vision["crop_boxes"] = crop_boxes
    valid = not issues
    cutout_review_sheet_path = None
    cache_dir = Path(cutout_cache_dir).resolve() if cutout_cache_dir else None
    if valid and cache_dir:
        cache_dir.mkdir(parents=True, exist_ok=True)
        _save_cached_cutouts(
            cache_dir,
            _sheet_signature(sheet_path),
            subjects,
        )
        cutout_paths = [str(path) for path in _cutout_cache_paths(cache_dir)[1]]
        cutout_review_sheet_path = _cutout_review_sheet_path(cache_dir)
        _build_cutout_review_sheet(subjects).save(cutout_review_sheet_path, format="PNG")
    else:
        cutout_paths = []
    return {
        "valid": valid,
        "max_attempts": SUBJECT_GENERATION_MAX_ATTEMPTS,
        "issues": issues,
        "cells": cells,
        "detected_count": vision["object_count"],
        "top_count": vision["top_count"],
        "bottom_count": vision["bottom_count"],
        "has_text": vision["has_text"],
        "cutout_review_sheet_path": str(cutout_review_sheet_path) if cutout_review_sheet_path else "",
        "cutout_paths": cutout_paths,
        "inspection_required": valid,
        "next_tool": "language_learning_review_subject_sheet" if valid else "language_learning_prepare_images",
        "vision": vision,
    }


def _extract_subjects(sheet: Image.Image, sheet_path: Path, cache_dir: Path | None) -> list[Image.Image]:
    """按识别位置裁切十个主体；同一主体图的结果写入本次生产缓存，中韩拼卡共用。"""
    signature = _sheet_signature(sheet_path)
    if cache_dir is not None:
        cached = _load_cached_cutouts(cache_dir, signature)
        if cached is not None:
            return cached
    raise CardCompositionError("透明主体切图尚未通过整图视觉验收，不能制作卡片")
