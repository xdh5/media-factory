"""按既定模板制作语言学习卡片。"""

import re
import unicodedata
from pathlib import Path

from PIL import Image, ImageDraw, ImageFont, ImageOps

from .filenames import safe_filename

from .._constants import CARD_CANVAS_SIZE, STATIC_ROOT, SUBJECT_ALPHA_THRESHOLD, SUBJECT_GRID_BOXES, SUBJECT_SHEET_ASPECT_MAX_PIXEL_ERROR, SUBJECT_SHEET_SIZE, TEMPLATE_FILENAMES, WORDS_PER_TASK
from .._errors import CardCompositionError

_FONTS = {
    "latin": [Path("/usr/share/fonts/windows/arialbd.ttf"), Path("C:/Windows/Fonts/arialbd.ttf"), Path("/usr/share/fonts/truetype/dejavu/DejaVuSans-Bold.ttf")],
    "cjk": [Path("/usr/share/fonts/windows/simhei.ttf"), Path("C:/Windows/Fonts/simhei.ttf"), Path("/usr/share/fonts/truetype/wqy/wqy-zenhei.ttc"), Path("/usr/share/fonts/opentype/noto/NotoSansCJK-Bold.ttc")],
    "korean": [Path("/usr/share/fonts/windows/malgunbd.ttf"), Path("C:/Windows/Fonts/malgunbd.ttf"), Path("/usr/share/fonts/opentype/noto/NotoSansCJK-Bold.ttc"), Path("/usr/share/fonts/truetype/wqy/wqy-zenhei.ttc")],
    "italic": [Path("/usr/share/fonts/windows/ariali.ttf"), Path("C:/Windows/Fonts/ariali.ttf"), Path("/usr/share/fonts/truetype/dejavu/DejaVuSans-Oblique.ttf")],
}
_LAYOUTS = {"en-ko": {"topic": (540, 581, 54), "box": (335, 716, 745, 984), "target": (540, 1139, 98), "pronunciation": (540, 1249, 47), "english": (540, 1046, 43)}, "en-zh": {"topic": (540, 581, 54), "box": (335, 716, 745, 984), "target": (540, 1139, 88), "pronunciation": (540, 1249, 47), "english": (540, 1046, 43)}}


def _font(kind: str, size: int):
    for path in _FONTS[kind]:
        if path.is_file():
            return ImageFont.truetype(str(path), size=size)
    raise CardCompositionError(f"找不到固定卡片所需的 {kind} 字体")


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


def _is_target_aspect(width: int, height: int) -> bool:
    """允许 16:9 横版有 1 像素舍入误差。"""
    if width <= 0 or height <= 0:
        return False
    expected = round(width * SUBJECT_SHEET_SIZE[1] / SUBJECT_SHEET_SIZE[0])
    return abs(height - expected) <= SUBJECT_SHEET_ASPECT_MAX_PIXEL_ERROR


def _sheet(path: Path) -> Image.Image:
    try:
        with Image.open(path) as source:
            if source.format != "PNG":
                raise CardCompositionError("主体素材必须是带透明通道的 PNG，不能使用 JPG 或 WebP")
            image = ImageOps.exif_transpose(source).convert("RGBA")
    except CardCompositionError:
        raise
    except Exception as exc:
        raise CardCompositionError("上传的文件不是有效的主体素材图") from exc
    if image.size != SUBJECT_SHEET_SIZE:
        if not _is_target_aspect(image.width, image.height):
            raise CardCompositionError(
                f"主体素材图必须是 16:9 横版。当前为 {image.width}×{image.height}，"
                f"请重新生成 16:9 透明 PNG；像素不必正好 {SUBJECT_SHEET_SIZE[0]}×{SUBJECT_SHEET_SIZE[1]}，程序会缩放到该尺寸后再切格"
            )
        image = image.resize(SUBJECT_SHEET_SIZE, Image.Resampling.LANCZOS)
    alpha = image.getchannel("A")
    if alpha.getextrema()[0] == 255 or alpha.getextrema()[1] == 0:
        raise CardCompositionError("主体素材没有有效的 Alpha 透明背景；请使用真正透明的 PNG")
    return image


def _visible_mask(image: Image.Image) -> Image.Image:
    return image.getchannel("A").point(lambda value: 255 if value > SUBJECT_ALPHA_THRESHOLD else 0)


def _extract_subjects(sheet: Image.Image) -> list[Image.Image]:
    """把已缩放到 1920×1080 的图按 2 行×5 列等分，再按 Alpha 包围盒裁出每格主体。"""
    subjects = []
    for index, grid_box in enumerate(SUBJECT_GRID_BOXES, 1):
        cell = sheet.crop(grid_box)
        bbox = _visible_mask(cell).getbbox()
        if bbox is None:
            raise CardCompositionError(f"第 {index} 格没有可见主体，请重新生成完整的 2 行×5 列主体图")
        subjects.append(cell.crop(bbox))
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


def compose_fixed_cards(subject_sheet_path: str | Path, words: list[dict], learning_mode: str, topic_english: str, output_dir: str | Path) -> dict:
    if learning_mode not in _LAYOUTS:
        raise CardCompositionError("不支持的固定模板语言方向")
    topic = re.sub(r"\s+", " ", str(topic_english or "").strip()).upper()
    if not topic:
        raise CardCompositionError("固定模板需要英文主题标题")
    template_path = STATIC_ROOT / TEMPLATE_FILENAMES[learning_mode]
    if not template_path.is_file():
        raise CardCompositionError(f"固定模板不存在：{template_path.name}")
    sheet, rows, layout = _sheet(Path(subject_sheet_path)), _words(words), _LAYOUTS[learning_mode]
    output = Path(output_dir).resolve()
    if output.suffix.lower() == ".zip":
        raise CardCompositionError("output_dir 必须是卡片文件夹，不要再传 zip 路径")
    if output.exists() and not output.is_dir():
        raise CardCompositionError(f"output_dir 已存在且不是文件夹：{output}")
    output.mkdir(parents=True, exist_ok=True)
    subjects = _extract_subjects(sheet)
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
            except ValueError as exc:
                raise CardCompositionError(str(exc)) from exc
            if name in used_names:
                raise CardCompositionError(f"卡片文件名冲突，标题必须唯一：{name}")
            used_names.add(name)
            path = output / name
            card.convert("RGB").save(path, format="PNG", optimize=True)
            card_paths.append(str(path))
    return {"output_dir": str(output), "card_paths": card_paths, "word_count": len(rows), "learning_mode": learning_mode}
