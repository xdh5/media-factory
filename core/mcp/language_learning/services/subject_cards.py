"""按既定模板制作语言学习卡片。"""

import re
import unicodedata
from pathlib import Path

from PIL import Image, ImageDraw, ImageFont, ImageOps

from core.paths import PROJECT_STATIC_ROOT
from core.tools.generate_final_video import safe_filename
from ..config import (
    CARD_CANVAS_SIZE,
    STATIC_ROOT,
    SUBJECT_FRAME_ORIGIN,
    SUBJECT_FRAME_SIZE,
    TEMPLATE_FILENAMES,
    WORDS_PER_TASK,
)
from ..errors import CardCompositionError
from .subject_cutouts import _extract_subjects, _sheet

_FONT_DIR = PROJECT_STATIC_ROOT / "font"
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
    raise CardCompositionError(f"找不到固定卡片所需的 {kind} 字体；请放到 core/static/font 或安装系统字体")


_SUBJECT_FRAME_BOX = (
    SUBJECT_FRAME_ORIGIN[0],
    SUBJECT_FRAME_ORIGIN[1],
    SUBJECT_FRAME_ORIGIN[0] + SUBJECT_FRAME_SIZE[0],
    SUBJECT_FRAME_ORIGIN[1] + SUBJECT_FRAME_SIZE[1],
)
_LAYOUTS = {"en-ko": {"topic": (540, 581, 54), "box": _SUBJECT_FRAME_BOX, "target": (540, 1139, 98), "pronunciation": (540, 1249, 47), "english": (540, 1046, 43)}, "en-zh": {"topic": (540, 581, 54), "box": _SUBJECT_FRAME_BOX, "target": (540, 1139, 88), "pronunciation": (540, 1249, 47), "english": (540, 1046, 43)}}


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


def fit_subject_into_frame(
    subject_width: int,
    subject_height: int,
    frame_size: tuple[int, int] = SUBJECT_FRAME_SIZE,
) -> dict:
    """按卡片主体区等比缩放并居中。网页预览必须复用同一取整规则。"""
    frame_width, frame_height = frame_size
    if subject_width < 1 or subject_height < 1 or frame_width < 1 or frame_height < 1:
        raise CardCompositionError("主体图或卡片主体区尺寸无效")
    scale = min(frame_width / subject_width, frame_height / subject_height)
    width = max(1, round(subject_width * scale))
    height = max(1, round(subject_height * scale))
    return {
        "width": width,
        "height": height,
        "left": (frame_width - width) // 2,
        "top": (frame_height - height) // 2,
    }


def _paste_subject(card: Image.Image, subject: Image.Image, box: tuple[int, int, int, int]) -> None:
    fitted_box = fit_subject_into_frame(subject.width, subject.height, (box[2] - box[0], box[3] - box[1]))
    fitted = subject.resize((fitted_box["width"], fitted_box["height"]), Image.Resampling.LANCZOS)
    card.alpha_composite(fitted, (box[0] + fitted_box["left"], box[1] + fitted_box["top"]))


def _draw(draw, value: str, spec: tuple[int, int, int], kind: str):
    draw.text(spec[:2], unicodedata.normalize("NFC", value.strip()), font=_font(kind, spec[2]), fill="#111111", anchor="mm")


def _draw_bilingual(draw, english: str, chinese: str, spec: tuple[int, int, int]):
    latin, cjk = _font("latin", spec[2]), _font("cjk", spec[2])
    english, chinese = english.strip().upper(), chinese.strip()
    left = spec[0] - (draw.textlength(english, font=latin) + spec[2] * .45 + draw.textlength(chinese, font=cjk)) / 2
    draw.text((left, spec[1]), english, font=latin, fill="#111111", anchor="lm")
    draw.text((left + draw.textlength(english, font=latin) + spec[2] * .45, spec[1]), chinese, font=cjk, fill="#111111", anchor="lm")


def _compose_cards_with_subjects(
    subjects: list[Image.Image],
    words: list[dict],
    learning_mode: str,
    topic_english: str,
    output_dir: str | Path,
) -> dict:
    """使用同一套模板渲染直接制作与预制包的单词卡。"""
    if len(subjects) != WORDS_PER_TASK:
        raise CardCompositionError(f"固定模板必须正好使用 {WORDS_PER_TASK} 张主体图")
    if learning_mode not in _LAYOUTS:
        raise CardCompositionError("不支持的固定模板语言方向")
    topic = re.sub(r"\s+", " ", str(topic_english or "").strip()).upper()
    if not topic:
        raise CardCompositionError("固定模板需要英文主题标题")
    rows, layout = _words(words), _LAYOUTS[learning_mode]
    template_path = STATIC_ROOT / TEMPLATE_FILENAMES[learning_mode]
    if not template_path.is_file():
        raise CardCompositionError(f"固定模板不存在：{template_path.name}")
    output = Path(output_dir).resolve()
    if output.suffix.lower() == ".zip":
        raise CardCompositionError("output_dir 必须是卡片文件夹，不要再传 zip 路径")
    if output.exists() and not output.is_dir():
        raise CardCompositionError(f"output_dir 已存在且不是文件夹：{output}")
    output.mkdir(parents=True, exist_ok=True)
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
                _draw_bilingual(draw, word["english"], word["chinese"], layout["english"])
                _draw(draw, word["korean"], layout["target"], "korean")
            else:
                _draw(draw, word["english"].upper(), layout["english"], "latin")
                _draw(draw, word["chinese"], layout["target"], "cjk")
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


def compose_fixed_cards(
    subject_sheet_path: str | Path,
    words: list[dict],
    learning_mode: str,
    topic_english: str,
    output_dir: str | Path,
    cutout_cache_dir: str | Path | None = None,
) -> dict:
    sheet_path = Path(subject_sheet_path)
    sheet = _sheet(sheet_path)
    cache_dir = Path(cutout_cache_dir).resolve() if cutout_cache_dir else None
    subjects = _extract_subjects(sheet, sheet_path, cache_dir)
    return _compose_cards_with_subjects(subjects, words, learning_mode, topic_english, output_dir)


def compose_fixed_cards_from_subjects(
    subject_paths: list[str | Path], words: list[dict], learning_mode: str, topic_english: str, output_dir: str | Path,
) -> dict:
    """直接使用十张已验收透明主体图拼卡，不重复执行定位和切图。"""
    if len(subject_paths) != WORDS_PER_TASK:
        raise CardCompositionError(f"预制词包必须提供 {WORDS_PER_TASK} 张主体图")
    subjects = []
    for index, value in enumerate(subject_paths, 1):
        path = Path(value).resolve()
        if not path.is_file():
            raise CardCompositionError(f"第 {index} 张预制主体图不存在：{path}")
        with Image.open(path) as source:
            subject = ImageOps.exif_transpose(source).convert("RGBA")
            alpha = subject.getchannel("A")
            if alpha.getextrema()[0] >= 255:
                raise CardCompositionError(f"第 {index} 张预制主体图没有透明背景，不能用于词包")
            subjects.append(subject.copy())
    return _compose_cards_with_subjects(subjects, words, learning_mode, topic_english, output_dir)
