"""按既定模板制作语言学习卡片。"""

import hashlib
import json
import re
import unicodedata
from pathlib import Path

from PIL import Image, ImageDraw, ImageFont, ImageOps

from core.tools.generate_final_video import safe_filename
from core.tools.qwen_vision import QwenVisionError, analyze_image

from .._constants import (
    CARD_CANVAS_SIZE,
    CARD_GRID_COLUMNS,
    PROJECT_ROOT,
    STATIC_ROOT,
    SUBJECT_ALPHA_THRESHOLD,
    SUBJECT_CUTOUT_STRATEGY_VERSION,
    SUBJECT_GENERATION_MAX_ATTEMPTS,
    SUBJECT_REMBG_MODEL,
    SUBJECT_SHEET_SIZE,
    TEMPLATE_FILENAMES,
    WORDS_PER_TASK,
)
from .._errors import CardCompositionError

_FONT_DIR = PROJECT_ROOT / "static" / "font"
_PROMPTS_DIR = Path(__file__).resolve().parent.parent / "prompts"
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


_REMBG_SESSION = None


def _rembg_session():
    """同一进程内复用 u2netp session，十格批处理只加载一次模型。"""
    global _REMBG_SESSION
    if _REMBG_SESSION is not None:
        return _REMBG_SESSION
    try:
        from rembg import new_session
    except ImportError as extra:
        raise CardCompositionError("缺少 rembg，请先安装项目依赖后再拼卡") from extra
    try:
        _REMBG_SESSION = new_session(SUBJECT_REMBG_MODEL)
    except Exception as extra:
        raise CardCompositionError(
            f"初始化 {SUBJECT_REMBG_MODEL} 抠图会话失败：{extra}。请确认已安装 rembg 且能下载模型"
        ) from extra
    return _REMBG_SESSION


def _sheet(path: Path) -> Image.Image:
    try:
        with Image.open(path) as source:
            image = ImageOps.exif_transpose(source).convert("RGB")
    except Exception as extra:
        raise CardCompositionError("上传的文件不是有效的主体素材图") from extra
    return _fit_sheet(image)


def _visible_mask(image: Image.Image) -> Image.Image:
    return image.getchannel("A").point(lambda value: 255 if value > SUBJECT_ALPHA_THRESHOLD else 0)


def _sheet_signature(path: Path) -> str:
    digest = hashlib.sha256()
    digest.update(SUBJECT_REMBG_MODEL.encode("utf-8"))
    digest.update(b"\0")
    digest.update(SUBJECT_CUTOUT_STRATEGY_VERSION.encode("utf-8"))
    digest.update(b"\0")
    digest.update(path.read_bytes())
    return digest.hexdigest()


def _cutout_cache_paths(cache_dir: Path) -> tuple[Path, list[Path]]:
    return cache_dir / "signature.txt", [cache_dir / f"{index:02d}.png" for index in range(1, WORDS_PER_TASK + 1)]


def _load_cached_cutouts(cache_dir: Path, signature: str) -> list[Image.Image] | None:
    marker, paths = _cutout_cache_paths(cache_dir)
    if not marker.is_file() or marker.read_text(encoding="utf-8").strip() != signature:
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
    for path, subject in zip(paths, subjects):
        subject.save(path, format="PNG")
    marker.write_text(signature, encoding="utf-8")


def _remove_subject_background(subject: Image.Image, session, index: int) -> Image.Image:
    """逐个主体抠图，避免整张图中较小或浅色主体被忽略。"""
    try:
        from rembg import remove
    except ImportError as extra:
        raise CardCompositionError("缺少 rembg，请先安装项目依赖后再拼卡") from extra
    try:
        cut = remove(subject.convert("RGB"), session=session)
    except Exception as extra:
        raise CardCompositionError(f"第 {index} 个主体 rembg 抠图失败：{extra}") from extra
    if not isinstance(cut, Image.Image):
        raise CardCompositionError(f"第 {index} 个主体 rembg 没有返回图片")
    return cut.convert("RGBA")


def _read_visual_prompt(name: str) -> str:
    path = _PROMPTS_DIR / name
    if not path.is_file():
        raise CardCompositionError(f"视觉验收 Prompt 不存在：{path}")
    return path.read_text(encoding="utf-8").strip()


def _visual_layout(subject_sheet_path: Path) -> dict:
    """让千问视觉只验收十个主体、上五下五和无文字。"""
    try:
        result = analyze_image(
            subject_sheet_path,
            _read_visual_prompt("visual-validation-system.md"),
            _read_visual_prompt("visual-validation-user.md"),
            json_output=True,
        )
    except QwenVisionError as exc:
        raise CardCompositionError(f"千问视觉验收失败：{exc}", exc.details) from exc
    raw = str(result.get("text") or "").strip().removeprefix("```json").removesuffix("```").strip()
    try:
        payload = json.loads(raw)
    except json.JSONDecodeError as exc:
        raise CardCompositionError(f"千问视觉没有返回有效 JSON：{raw[:300]}") from exc
    if not isinstance(payload, dict):
        raise CardCompositionError("千问视觉验收结果必须是 JSON 对象")
    try:
        object_count = int(payload["object_count"])
        top_count = int(payload["top_count"])
        bottom_count = int(payload["bottom_count"])
    except (KeyError, TypeError, ValueError) as exc:
        raise CardCompositionError("千问视觉验收结果缺少有效的 object_count、top_count 或 bottom_count") from exc
    has_text = payload.get("has_text")
    if not isinstance(has_text, bool):
        raise CardCompositionError("千问视觉验收结果的 has_text 必须是布尔值")
    raw_boxes = payload.get("boxes")
    boxes: list[list[int]] = []
    if not isinstance(raw_boxes, list) or len(raw_boxes) != WORDS_PER_TASK:
        raise CardCompositionError(f"千问视觉验收结果的 boxes 必须正好包含 {WORDS_PER_TASK} 个边界框")
    for index, raw_box in enumerate(raw_boxes, 1):
        if not isinstance(raw_box, list) or len(raw_box) != 4:
            raise CardCompositionError(f"千问视觉返回的第 {index} 个边界框格式不正确")
        try:
            box = [max(0, min(1000, int(value))) for value in raw_box]
        except (TypeError, ValueError) as exc:
            raise CardCompositionError(f"千问视觉返回的第 {index} 个边界框坐标不是整数") from exc
        if box[2] <= box[0] or box[3] <= box[1]:
            raise CardCompositionError(f"千问视觉返回的第 {index} 个边界框范围无效")
        boxes.append(box)
    issues: list[str] = []
    if object_count != WORDS_PER_TASK:
        issues.append(f"视觉模型判断主体总数为 {object_count}，必须为 {WORDS_PER_TASK}")
    if top_count != CARD_GRID_COLUMNS or bottom_count != CARD_GRID_COLUMNS:
        issues.append(
            f"视觉模型判断上排 {top_count} 个、下排 {bottom_count} 个，"
            f"必须各为 {CARD_GRID_COLUMNS} 个"
        )
    if has_text:
        issues.append("视觉模型检测到可见文字、字母、数字、标签或水印")
    return {
        "valid": not issues,
        "object_count": object_count,
        "top_count": top_count,
        "bottom_count": bottom_count,
        "has_text": has_text,
        "reason": str(payload.get("reason") or "").strip(),
        "boxes": boxes,
        "issues": issues,
        "model": str(result.get("model") or ""),
        "usage": dict(result.get("usage") or {}),
        "image_size": dict(result.get("image_size") or {}),
    }


def _detect_subjects(sheet: Image.Image, session, visual_boxes: list[list[int]]) -> tuple[list[Image.Image], list[dict], list[str]]:
    """按视觉模型返回的十个边界框逐个裁切和抠图。"""
    issues: list[str] = []
    subjects: list[Image.Image] = []
    cells: list[dict] = []
    for index, visual_box in enumerate(visual_boxes, 1):
        box = (
            visual_box[0] * sheet.width // 1000,
            visual_box[1] * sheet.height // 1000,
            max(1, visual_box[2] * sheet.width // 1000),
            max(1, visual_box[3] * sheet.height // 1000),
        )
        region = _remove_subject_background(sheet.crop(box), session, index)
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
    return subjects, cells, issues


def validate_subject_sheet(
    subject_sheet_path: str | Path,
    cutout_cache_dir: str | Path | None = None,
) -> dict:
    """先用千问视觉验收十个主体、上五下五和无文字，再由 Python 分组裁切。"""
    sheet_path = Path(subject_sheet_path).resolve()
    sheet = _sheet(sheet_path)
    vision = _visual_layout(sheet_path)
    issues = list(vision["issues"])
    subjects: list[Image.Image] = []
    cells: list[dict] = []
    if not issues:
        session = _rembg_session()
        subjects, cells, crop_issues = _detect_subjects(sheet, session, vision["boxes"])
        issues.extend(crop_issues)
    valid = not issues
    if valid and cutout_cache_dir:
        _save_cached_cutouts(
            Path(cutout_cache_dir).resolve(),
            _sheet_signature(sheet_path),
            subjects,
        )
    return {
        "valid": valid,
        "max_attempts": SUBJECT_GENERATION_MAX_ATTEMPTS,
        "issues": issues,
        "cells": cells,
        "detected_count": vision["object_count"],
        "top_count": vision["top_count"],
        "bottom_count": vision["bottom_count"],
        "has_text": vision["has_text"],
        "vision": vision,
    }


def _extract_subjects(sheet: Image.Image, sheet_path: Path, cache_dir: Path | None) -> list[Image.Image]:
    """按识别位置裁切十个主体；同一主体图的结果写入本次生产缓存，中韩拼卡共用。"""
    signature = _sheet_signature(sheet_path)
    if cache_dir is not None:
        cached = _load_cached_cutouts(cache_dir, signature)
        if cached is not None:
            return cached
    raise CardCompositionError("主体裁切缓存不存在；请先调用主体图视觉验收再制作卡片")


def _paste_subject(card: Image.Image, subject: Image.Image, box: tuple[int, int, int, int]) -> None:
    target = (box[2] - box[0], box[3] - box[1])
    fitted = ImageOps.contain(subject, target, Image.Resampling.LANCZOS)
    card.alpha_composite(fitted, (box[0] + (target[0] - fitted.width) // 2, box[1] + (target[1] - fitted.height) // 2))


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
