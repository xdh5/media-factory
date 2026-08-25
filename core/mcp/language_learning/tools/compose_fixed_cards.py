"""按既定模板制作语言学习卡片。"""

import hashlib
import json
import re
import unicodedata
from pathlib import Path
from statistics import median

from PIL import Image, ImageChops, ImageDraw, ImageFont, ImageOps

from core.tools.generate_final_video import safe_filename
from .._constants import (
    CARD_CANVAS_SIZE,
    CARD_GRID_COLUMNS,
    PROJECT_ROOT,
    STATIC_ROOT,
    SUBJECT_ALPHA_THRESHOLD,
    SUBJECT_CHROMA_HIGH_DISTANCE,
    SUBJECT_CHROMA_LOW_DISTANCE,
    SUBJECT_CUTOUT_STRATEGY_VERSION,
    SUBJECT_GENERATION_MAX_ATTEMPTS,
    SUBJECT_SHEET_SIZE,
    TEMPLATE_FILENAMES,
    WORDS_PER_TASK,
)
from .._errors import CardCompositionError

_FONT_DIR = PROJECT_ROOT / "static" / "font"
_SYSTEM_FONTS = {
    "latin": [Path("/usr/share/fonts/windows/arialbd.ttf"), Path("C:/Windows/Fonts/arialbd.ttf"), Path("/usr/share/fonts/truetype/dejavu/DejaVuSans-Bold.ttf")],
    "cjk": [Path("/usr/share/fonts/windows/simhei.ttf"), Path("C:/Windows/Fonts/simhei.ttf"), Path("/usr/share/fonts/truetype/wqy/wqy-zenhei.ttc"), Path("/usr/share/fonts/opentype/noto/NotoSansCJK-Bold.ttc")],
    "korean": [Path("/usr/share/fonts/windows/malgunbd.ttf"), Path("C:/Windows/Fonts/malgunbd.ttf"), Path("/usr/share/fonts/opentype/noto/NotoSansCJK-Bold.ttc"), Path("/usr/share/fonts/truetype/wqy/wqy-zenhei.ttc")],
    "italic": [Path("/usr/share/fonts/windows/ariali.ttf"), Path("C:/Windows/Fonts/ariali.ttf"), Path("/usr/share/fonts/truetype/dejavu/DejaVuSans-Oblique.ttf"), Path("ARIAL.TTF")],
}


def _font(kind: str, size: int):
    seen: set[Path] = set()
    candidates: list[Path] = []
    for path in _SYSTEM_FONTS[kind]:
        bundled = _FONT_DIR / path.name
        if bundled not in seen:
            candidates.append(bundled)
            seen.add(bundled)
        if path not in seen:
            candidates.append(path)
            seen.add(path)
    for path in candidates:
        if path.is_file():
            return ImageFont.truetype(str(path), size=size)
    raise CardCompositionError(f"找不到固定卡片所需的 {kind} 字体；请放到 static/font 或安装系统字体")


_LAYOUTS = {"en-ko": {"topic": (540, 581, 54), "box": (335, 716, 745, 984), "target": (540, 1139, 98), "pronunciation": (540, 1249, 47), "english": (540, 1046, 43)}, "en-zh": {"topic": (540, 581, 54), "box": (335, 716, 745, 984), "target": (540, 1139, 88), "pronunciation": (540, 1249, 47), "english": (540, 1046, 43)}}


def _words(words: list[dict]) -> list[dict]:
    if len(words) != WORDS_PER_TASK:
        raise CardCompositionError(f"固定模板必须正好使用 {WORDS_PER_TASK} 个单词，现在是 {len(words)} 个")
    rows = []
    for index, item in enumerate(words, 1):
        row = {key: str(item.get(key) or "").strip() for key in ("english", "chinese", "korean", "romanization")}
        if not all(row.values()):
            raise CardCompositionError(f"第 {index} 个单词字段不完整")
        rows.append(row)
    return rows


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


def _background_removed_sheet_path(cache_dir: Path) -> Path:
    """返回整张去背景色主题图的缓存路径，供失败诊断复用。"""
    return cache_dir / "subject-sheet-background-removed.png"


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
    """记录整张去背景主题图的视觉验收结论，未通过时禁止拼卡。"""
    sheet_path = Path(subject_sheet_path).resolve()
    cache_dir = Path(cutout_cache_dir).resolve()
    signature = _sheet_signature(sheet_path)
    marker, cutout_paths = _cutout_cache_paths(cache_dir)
    if not marker.is_file() or marker.read_text(encoding="utf-8").strip() != signature:
        raise CardCompositionError("当前主体图没有可检查的抠图缓存，请先调用主体图验收")
    background_removed_path = _background_removed_sheet_path(cache_dir)
    if not background_removed_path.is_file():
        raise CardCompositionError("去背景后的完整主题图不存在，请先调用主体图验收")
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
        raise CardCompositionError("十张抠图缓存不完整，请重新执行主体图验收")
    inspection_path, history_path = _inspection_paths(cache_dir)
    if valid:
        inspection_path.write_text(
            json.dumps({"signature": signature, "approved": True, "review": normalized}, ensure_ascii=False, indent=2),
            encoding="utf-8",
        )
        return {
            "approved": True,
            "review": normalized,
            "background_removed_sheet_path": str(background_removed_path),
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
    regeneration_instruction = (
        "换一种与上一张明显不同、且与全部主体颜色反差更大的均匀纯色背景重新生成"
        if failure_kind == "background_edge"
        else "按验收问题重新生成主题图"
    )
    return {
        "approved": False,
        "review": normalized,
        "failed_rounds": failed_rounds,
        "action": "regenerate",
        "validation_issues": validation_issues,
        "regeneration_instruction": regeneration_instruction,
        "next_tool": "language_learning_prepare_images",
    }


def _estimate_background_rgb(sheet: Image.Image) -> tuple[int, int, int]:
    """从画布四边估计宿主 Agent 识别的均匀纯色背景实际 RGB。"""
    rgb = sheet.convert("RGB")
    pixels = rgb.load()
    stride = max(1, min(rgb.size) // 180)
    samples: list[tuple[int, int, int]] = []
    for x in range(0, rgb.width, stride):
        samples.extend((pixels[x, 0], pixels[x, rgb.height - 1]))
    for y in range(0, rgb.height, stride):
        samples.extend((pixels[0, y], pixels[rgb.width - 1, y]))
    if not samples:
        raise CardCompositionError("无法从主体图画布边缘估计背景色")
    return tuple(round(median(channel)) for channel in zip(*samples))


def _remove_sheet_background(sheet: Image.Image) -> tuple[Image.Image, tuple[int, int, int]]:
    """在整张图全局删除与背景同色或近似色的像素，不保护主体内部同色区域。"""
    rgb = sheet.convert("RGB")
    background_rgb = _estimate_background_rgb(rgb)
    background = Image.new("RGB", rgb.size, background_rgb)
    red, green, blue = ImageChops.difference(rgb, background).split()
    distance = ImageChops.lighter(ImageChops.lighter(red, green), blue)
    spread = max(1, SUBJECT_CHROMA_HIGH_DISTANCE - SUBJECT_CHROMA_LOW_DISTANCE)
    alpha = distance.point(
        lambda value: 0
        if value <= SUBJECT_CHROMA_LOW_DISTANCE
        else 255
        if value >= SUBJECT_CHROMA_HIGH_DISTANCE
        else round((value - SUBJECT_CHROMA_LOW_DISTANCE) * 255 / spread)
    )
    transparent = rgb.convert("RGBA")
    transparent.putalpha(alpha)
    return transparent, background_rgb


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
        "background_color": "",
        "reason": str(payload.get("reason") or "").strip(),
        "boxes": boxes,
        "issues": issues,
        "source": "host_agent",
    }


def _detect_subjects(
    sheet: Image.Image,
    visual_boxes: list[list[int]],
) -> tuple[list[Image.Image], list[dict], list[str], list[list[int]], tuple[int, int, int]]:
    """全局删除纯色背景后，严格按宿主 Agent 的框逐个紧裁主体。"""
    issues: list[str] = []
    subjects: list[Image.Image] = []
    cells: list[dict] = []
    crop_boxes = visual_boxes
    transparent_sheet, background_rgb = _remove_sheet_background(sheet)
    for index, crop_box in enumerate(crop_boxes, 1):
        box = (
            crop_box[0] * sheet.width // 1000,
            crop_box[1] * sheet.height // 1000,
            max(1, crop_box[2] * sheet.width // 1000),
            max(1, crop_box[3] * sheet.height // 1000),
        )
        region = transparent_sheet.crop(box)
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
        bbox = (
            box[0] + local_bbox[0],
            box[1] + local_bbox[1],
            box[0] + local_bbox[2],
            box[1] + local_bbox[3],
        )
        subject = region.crop(local_bbox)
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
    return subjects, cells, issues, crop_boxes, background_rgb


def validate_subject_sheet(
    subject_sheet_path: str | Path,
    visual_layout: dict,
    cutout_cache_dir: str | Path | None = None,
) -> dict:
    """使用宿主 Agent 的视觉结果验收，再由 Python 去背景并裁切。"""
    sheet_path = Path(subject_sheet_path).resolve()
    sheet = _sheet(sheet_path)
    vision = _validated_visual_layout(visual_layout)
    issues = list(vision["issues"])
    subjects: list[Image.Image] = []
    cells: list[dict] = []
    crop_boxes: list[list[int]] = []
    background_rgb: tuple[int, int, int] | None = None
    if not issues:
        subjects, cells, crop_issues, crop_boxes, background_rgb = _detect_subjects(
            sheet,
            vision["boxes"],
        )
        issues.extend(crop_issues)
    vision["crop_boxes"] = crop_boxes
    valid = not issues
    background_removed_sheet_path = None
    cache_dir = Path(cutout_cache_dir).resolve() if cutout_cache_dir else None
    if cache_dir:
        cache_dir.mkdir(parents=True, exist_ok=True)
        background_removed_sheet, saved_background_rgb = _remove_sheet_background(sheet)
        background_rgb = background_rgb or saved_background_rgb
        background_removed_sheet_path = _background_removed_sheet_path(cache_dir)
        background_removed_sheet.save(background_removed_sheet_path, format="PNG")
    vision["background_rgb"] = list(background_rgb) if background_rgb else []
    if valid and cache_dir:
        _save_cached_cutouts(
            cache_dir,
            _sheet_signature(sheet_path),
            subjects,
        )
        cutout_paths = [str(path) for path in _cutout_cache_paths(cache_dir)[1]]
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
        "background_removed": background_rgb is not None,
        "background_removed_sheet_path": (
            str(background_removed_sheet_path) if background_removed_sheet_path else ""
        ),
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
    raise CardCompositionError("主体抠图尚未通过整图视觉验收，不能制作卡片")


def _paste_subject(card: Image.Image, subject: Image.Image, box: tuple[int, int, int, int]) -> None:
    target_width = box[2] - box[0]
    target_height = box[3] - box[1]
    scale = min(target_width / subject.width, target_height / subject.height)
    fitted_width = max(1, round(subject.width * scale))
    fitted_height = max(1, round(subject.height * scale))
    fitted = subject.resize((fitted_width, fitted_height), Image.Resampling.LANCZOS)
    left = box[0] + (target_width - fitted_width) // 2
    top = box[1] + (target_height - fitted_height) // 2
    card.alpha_composite(fitted, (left, top))


def _draw(draw, value: str, spec: tuple[int, int, int], kind: str):
    draw.text(spec[:2], unicodedata.normalize("NFC", value.strip()), font=_font(kind, spec[2]), fill="#111111", anchor="mm")


def _draw_bilingual(draw, english: str, chinese: str, spec: tuple[int, int, int]):
    latin, cjk = _font("latin", spec[2]), _font("cjk", spec[2])
    english, chinese = english.strip().upper(), chinese.strip()
    left = spec[0] - (draw.textlength(english, font=latin) + spec[2] * .45 + draw.textlength(chinese, font=cjk)) / 2
    draw.text((left, spec[1]), english, font=latin, fill="#111111", anchor="lm")
    draw.text((left + draw.textlength(english, font=latin) + spec[2] * .45, spec[1]), chinese, font=cjk, fill="#111111", anchor="lm")


def compose_fixed_cards(
    subject_sheet_path: str | Path,
    words: list[dict],
    learning_mode: str,
    topic_english: str,
    output_dir: str | Path,
    cutout_cache_dir: str | Path | None = None,
) -> dict:
    if learning_mode not in _LAYOUTS:
        raise CardCompositionError("不支持的固定模板语言方向")
    topic = re.sub(r"\s+", " ", str(topic_english or "").strip()).upper()
    if not topic:
        raise CardCompositionError("固定模板需要英文主题标题")
    template_path = STATIC_ROOT / TEMPLATE_FILENAMES[learning_mode]
    if not template_path.is_file():
        raise CardCompositionError(f"固定模板不存在：{template_path.name}")
    sheet_path = Path(subject_sheet_path)
    sheet, rows, layout = _sheet(sheet_path), _words(words), _LAYOUTS[learning_mode]
    output = Path(output_dir).resolve()
    if output.suffix.lower() == ".zip":
        raise CardCompositionError("output_dir 必须是卡片文件夹，不要再传 zip 路径")
    if output.exists() and not output.is_dir():
        raise CardCompositionError(f"output_dir 已存在且不是文件夹：{output}")
    output.mkdir(parents=True, exist_ok=True)
    cache_dir = Path(cutout_cache_dir).resolve() if cutout_cache_dir else None
    subjects = _extract_subjects(sheet, sheet_path, cache_dir)
    card_paths = []
    with Image.open(template_path) as source:
        template = ImageOps.fit(ImageOps.exif_transpose(source).convert("RGB"), CARD_CANVAS_SIZE, method=Image.Resampling.LANCZOS)
        used_names: set[str] = set()
        for word, subject in zip(rows, subjects):
            card = template.copy().convert("RGBA")
            _paste_subject(card, subject, layout["box"])
            draw = ImageDraw.Draw(card)
            _draw(draw, f"{topic} {'IN KOREAN' if learning_mode == 'en-ko' else 'IN CHINESE'}", layout["topic"], "latin")
            if learning_mode == "en-ko":
                _draw_bilingual(draw, word["english"], word["chinese"], layout["english"]); _draw(draw, word["korean"], layout["target"], "korean")
            else:
                _draw(draw, word["english"].upper(), layout["english"], "latin"); _draw(draw, word["chinese"], layout["target"], "cjk")
            _draw(draw, f"[{word['romanization']}]", layout["pronunciation"], "italic")
            try:
                name = f"{safe_filename(word['english'])}.png"
            except Exception as exc:
                raise CardCompositionError(str(exc)) from exc
            if name in used_names:
                raise CardCompositionError(f"卡片文件名冲突，标题必须唯一：{name}")
            used_names.add(name)
            path = output / name
            card.convert("RGB").save(path, format="PNG", optimize=True)
            card_paths.append(str(path))
    return {"output_dir": str(output), "card_paths": card_paths, "word_count": len(rows), "learning_mode": learning_mode}
