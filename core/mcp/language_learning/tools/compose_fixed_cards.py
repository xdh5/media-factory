"""按既定模板制作语言学习卡片。"""

import hashlib
import re
import unicodedata
from collections import deque
from pathlib import Path

from PIL import Image, ImageDraw, ImageFilter, ImageFont, ImageOps

from core.tools.generate_final_video import safe_filename

from .._constants import (
    CARD_CANVAS_SIZE,
    CARD_GRID_COLUMNS,
    PROJECT_ROOT,
    STATIC_ROOT,
    SUBJECT_ALPHA_THRESHOLD,
    SUBJECT_CUTOUT_STRATEGY_VERSION,
    SUBJECT_DETECTION_ANALYSIS_WIDTH,
    SUBJECT_DETECTION_DILATION_SIZE,
    SUBJECT_DETECTION_MIN_COMPONENT_PIXELS,
    SUBJECT_GENERATION_MAX_ATTEMPTS,
    SUBJECT_REMBG_MODEL,
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


def _remove_sheet_background(sheet: Image.Image, session) -> Image.Image:
    try:
        from rembg import remove
    except ImportError as extra:
        raise CardCompositionError("缺少 rembg，请先安装项目依赖后再拼卡") from extra
    try:
        cut = remove(sheet.convert("RGB"), session=session)
    except Exception as extra:
        raise CardCompositionError(f"整张主体图 rembg 抠图失败：{extra}") from extra
    if not isinstance(cut, Image.Image):
        raise CardCompositionError("整张主体图 rembg 没有返回图片")
    return cut.convert("RGBA")


def _component_boxes(mask: Image.Image) -> list[tuple[int, int, int, int]]:
    """在缩小后的蒙版中查找独立主体，忽略极小的抠图噪点。"""
    analysis_width = min(SUBJECT_DETECTION_ANALYSIS_WIDTH, mask.width)
    analysis_height = max(1, round(mask.height * analysis_width / mask.width))
    small = mask.resize((analysis_width, analysis_height), Image.Resampling.NEAREST)
    small = small.filter(ImageFilter.MaxFilter(SUBJECT_DETECTION_DILATION_SIZE))
    pixels = small.tobytes()
    visited = bytearray(len(pixels))
    boxes: list[tuple[int, int, int, int]] = []
    for start, value in enumerate(pixels):
        if value == 0 or visited[start]:
            continue
        queue = deque([start])
        visited[start] = 1
        area = 0
        min_x = max_x = start % analysis_width
        min_y = max_y = start // analysis_width
        while queue:
            current = queue.popleft()
            x = current % analysis_width
            y = current // analysis_width
            area += 1
            min_x, max_x = min(min_x, x), max(max_x, x)
            min_y, max_y = min(min_y, y), max(max_y, y)
            if x > 0:
                neighbor = current - 1
                if pixels[neighbor] and not visited[neighbor]:
                    visited[neighbor] = 1
                    queue.append(neighbor)
            if x + 1 < analysis_width:
                neighbor = current + 1
                if pixels[neighbor] and not visited[neighbor]:
                    visited[neighbor] = 1
                    queue.append(neighbor)
            if y > 0:
                neighbor = current - analysis_width
                if pixels[neighbor] and not visited[neighbor]:
                    visited[neighbor] = 1
                    queue.append(neighbor)
            if y + 1 < analysis_height:
                neighbor = current + analysis_width
                if pixels[neighbor] and not visited[neighbor]:
                    visited[neighbor] = 1
                    queue.append(neighbor)
        if area >= SUBJECT_DETECTION_MIN_COMPONENT_PIXELS:
            left = max(0, min_x * mask.width // analysis_width)
            top = max(0, min_y * mask.height // analysis_height)
            right = min(mask.width, (max_x + 1) * mask.width // analysis_width + 1)
            bottom = min(mask.height, (max_y + 1) * mask.height // analysis_height + 1)
            boxes.append((left, top, right, bottom))
    return boxes


def _detect_subjects(sheet: Image.Image, session) -> tuple[list[Image.Image], list[dict], list[str]]:
    """整图识别主体，按上五下五、从左到右排序并裁切。"""
    cut = _remove_sheet_background(sheet, session)
    mask = _visible_mask(cut)
    boxes = _component_boxes(mask)
    detected: list[tuple[tuple[int, int, int, int], Image.Image]] = []
    for box in boxes:
        region = cut.crop(box)
        local_bbox = _visible_mask(region).getbbox()
        if local_bbox is None:
            continue
        full_bbox = (
            box[0] + local_bbox[0],
            box[1] + local_bbox[1],
            box[0] + local_bbox[2],
            box[1] + local_bbox[3],
        )
        detected.append((full_bbox, region.crop(local_bbox)))
    top = [item for item in detected if (item[0][1] + item[0][3]) / 2 < sheet.height / 2]
    bottom = [item for item in detected if (item[0][1] + item[0][3]) / 2 >= sheet.height / 2]
    top.sort(key=lambda item: (item[0][0] + item[0][2]) / 2)
    bottom.sort(key=lambda item: (item[0][0] + item[0][2]) / 2)
    ordered = [*top, *bottom]
    issues: list[str] = []
    if len(detected) != WORDS_PER_TASK:
        issues.append(f"必须识别到 {WORDS_PER_TASK} 个独立主体，实际识别到 {len(detected)} 个")
    if len(top) != CARD_GRID_COLUMNS or len(bottom) != CARD_GRID_COLUMNS:
        issues.append(
            f"主体必须上排 {CARD_GRID_COLUMNS} 个、下排 {CARD_GRID_COLUMNS} 个，"
            f"实际为上排 {len(top)} 个、下排 {len(bottom)} 个"
        )
    cells = []
    for index, (bbox, subject) in enumerate(ordered, 1):
        foreground_pixels = _visible_mask(subject).histogram()[255]
        cells.append({
            "index": index,
            "valid": not issues,
            "bbox": list(bbox),
            "foreground_ratio": round(foreground_pixels / (sheet.width * sheet.height), 4),
            "issues": [],
        })
    return [subject for _, subject in ordered], cells, issues


def validate_subject_sheet(
    subject_sheet_path: str | Path,
    cutout_cache_dir: str | Path | None = None,
) -> dict:
    """用 Python 检查是否恰好识别到上五下五共十个主体，不做文字识别。"""
    sheet_path = Path(subject_sheet_path).resolve()
    sheet = _sheet(sheet_path)
    session = _rembg_session()
    subjects, cells, issues = _detect_subjects(sheet, session)
    top_count = sum(1 for item in cells if ((item["bbox"][1] + item["bbox"][3]) / 2) < sheet.height / 2)
    bottom_count = len(cells) - top_count
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
        "detected_count": len(cells),
        "top_count": top_count,
        "bottom_count": bottom_count,
    }


def _extract_subjects(sheet: Image.Image, sheet_path: Path, cache_dir: Path | None) -> list[Image.Image]:
    """按识别位置裁切十个主体；同一主体图的结果写入本次生产缓存，中韩拼卡共用。"""
    signature = _sheet_signature(sheet_path)
    if cache_dir is not None:
        cached = _load_cached_cutouts(cache_dir, signature)
        if cached is not None:
            return cached
    session = _rembg_session()
    subjects, _, issues = _detect_subjects(sheet, session)
    if issues:
        raise CardCompositionError("；".join(issues))
    if cache_dir is not None:
        _save_cached_cutouts(cache_dir, signature, subjects)
    return subjects


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
