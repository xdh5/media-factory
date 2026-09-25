"""拼镜头后合配音；字幕、贴纸、BGM、封面均可选。"""

from __future__ import annotations

import hashlib
import json
import time
from pathlib import Path
from typing import Callable
from uuid import uuid4

from core.tools.generate_sticker import generate_sticker
from core.tools.generate_subtitles import generate_subtitles
from core.tools.generate_emphasis_lines import generate_emphasis_lines
from core.tools.generate_subtitles._constants import SUBTITLE_DEFAULT_FONT_SIZE

from ._bilingual import translate_cue_texts
from ._compose_shots import compose_shots
from ._mix_body import mix_body
from ._errors import InvalidParameterError
from ._ffmpeg import _encode_video_args, _executable, _probe, _run
from ._size import parse_size

__all__ = ["generate_final_video"]

ProgressCallback = Callable[[str], None]


def _file_sha256(path: Path) -> str:
    digest = hashlib.sha256()
    with path.open("rb") as source:
        for chunk in iter(lambda: source.read(1024 * 1024), b""):
            digest.update(chunk)
    return digest.hexdigest()


def _normalize_composed_video(source_path: str | Path, output_path: Path) -> tuple[str, bool]:
    """把拼接片规范为恒定 30 帧，并按源内容指纹复用中间片。"""
    source = Path(source_path).resolve()
    fingerprint = _file_sha256(source)
    metadata_path = output_path.with_suffix(".json")
    if output_path.is_file() and metadata_path.is_file():
        try:
            metadata = json.loads(metadata_path.read_text(encoding="utf-8"))
            if metadata.get("source_sha256") == fingerprint and _probe(output_path)["duration"] > 0:
                return str(output_path), True
        except (OSError, ValueError, json.JSONDecodeError):
            pass
    probe = _probe(source)
    temporary = output_path.with_name(f".{output_path.stem}-{uuid4().hex}.tmp.mp4")
    command = [
        _executable("ffmpeg"), "-y", "-i", str(source),
        "-an", "-fps_mode", "cfr", "-r", "30",
        *_encode_video_args(still_image=False),
        "-movflags", "+faststart", str(temporary),
    ]
    try:
        _run(command, "规范化镜头时间戳", timeout_seconds=max(600, probe["duration"] * 15))
        _probe(temporary)
        for attempt in range(6):
            try:
                temporary.replace(output_path)
                break
            except OSError:
                if attempt == 5:
                    raise
                time.sleep(1.0)
                output_path.unlink(missing_ok=True)
        metadata_path.write_text(
            json.dumps({"source_sha256": fingerprint}, ensure_ascii=False, indent=2),
            encoding="utf-8",
        )
    finally:
        temporary.unlink(missing_ok=True)
    return str(output_path), False


def _compose_item(shot: dict) -> dict:
    item = {"id": shot["id"]}
    segment = str(shot.get("segment_path") or "").strip()
    if segment:
        item["segment_path"] = segment
        return item
    item["image_path"] = shot["image_path"]
    for key in ("duration", "motion"):
        if shot.get(key) is not None:
            item[key] = shot[key]
    return item


def _subtitle_cues(shots: list[dict], shot_results: list[dict]) -> list[dict]:
    by_id = {str(shot.get("id") or "").strip(): shot for shot in shots}
    cues: list[dict] = []
    cursor = 0.0
    for result in shot_results:
        source = by_id.get(str(result["id"])) or {}
        duration = float(result.get("duration") or 0)
        language = str(source.get("subtitle_language") or "zh")
        lines = source.get("subtitle_lines")
        if isinstance(lines, list) and lines:
            for item in lines:
                if not isinstance(item, dict):
                    continue
                text = item.get("text")
                if isinstance(text, list):
                    if not text:
                        continue
                else:
                    text = str(text or "").strip()
                    if not text:
                        continue
                start = cursor + max(0.0, float(item.get("start") or 0))
                end = cursor + min(duration, float(item.get("end") or duration))
                if end <= start:
                    end = min(cursor + duration, start + 0.08)
                cue = {
                    "start": round(start, 3),
                    "end": round(end, 3),
                    "text": text,
                    "language": language,
                }
                if isinstance(item.get("ends_sentence"), bool):
                    cue["ends_sentence"] = item["ends_sentence"]
                position = item.get("position")
                if isinstance(position, dict) and position:
                    cue["position"] = position
                cues.append(cue)
        else:
            text = str(source.get("subtitle") or "").strip()
            if text:
                cues.append({
                    "start": cursor,
                    "end": cursor + duration,
                    "text": text,
                    "language": language,
                })
        cursor += duration
    return cues


def _secondary_subtitle_ass(
    cues: list[dict],
    settings: dict,
    subtitle_style: dict | None,
    cache_root: Path,
    width: int,
    height: int,
    progress: ProgressCallback | None,
) -> str | None:
    """中文 karaoke 字幕下方的英文翻译层；失败或无内容返回 None。"""
    enabled = bool(settings.get("enabled", True))
    if not enabled or not cues:
        return None
    translatable = [
        cue for cue in cues
        if str(cue.get("language") or "zh") == "zh" and "position" not in cue
    ]
    if not translatable:
        return None
    texts: list[str] = []
    for cue in translatable:
        text = cue["text"]
        if isinstance(text, list):
            text = " ".join(str(item) for item in text)
        texts.append(str(text).strip())
    if progress:
        progress("正在翻译英文字幕")
    translations = translate_cue_texts(texts, progress=progress)
    en_pairs = [
        (cue, translation)
        for cue, translation in zip(translatable, translations)
        if translation
    ]
    if not en_pairs:
        if progress:
            progress("英文字幕翻译全部失败，跳过英文层")
        return None
    ratio = float(settings.get("font_size_ratio") or 0.4)
    chinese_font_size = int((subtitle_style or {}).get("font_size") or SUBTITLE_DEFAULT_FONT_SIZE)
    style = {
        "font_size": max(12, round(chinese_font_size * ratio)),
        **(settings.get("style") or {}),
    }
    position = settings.get("position") or None
    follow_chinese = None
    if isinstance(position, dict) and position.get("follow_chinese"):
        # 英文跟在中文块正下方：按每条中文的换行行数算 y（\pos 绝对定位，an5 居中锚点）。
        follow_chinese = dict(position)
        position = None
        follow_chinese.setdefault("gap", 25)
    if progress:
        progress("正在生成英文字幕图层")
    en_cues: list[dict] = []
    if follow_chinese is not None:
        gap = float(follow_chinese["gap"])
        # 与 generate_subtitles 同口径推算中文换行行数：
        # 逻辑宽 = 可用宽×2/字号（CJK 每字 2 个逻辑单位），逐字贪心断行，块内最多 2 行。
        from core.tools.generate_subtitles._text import _line_width

        available_width = width * 0.8
        max_width = max(1, round(available_width * 2 / max(1, chinese_font_size)))
        zh_bottom_offset = 0.32 * chinese_font_size  # 中文块下缘相对锚点(540)的距离（实测校准）

        def _zh_line_count(text: str) -> int:
            used = 0
            lines = 1
            for ch in text:
                unit_width = _line_width(ch)
                if used and used + unit_width > max_width:
                    lines += 1
                    used = unit_width
                else:
                    used += unit_width
            return min(2, lines)

        for cue, translation in en_pairs:
            zh_text = cue["text"]
            if isinstance(zh_text, list):
                zh_text = "".join(
                    str(span.get("text") if isinstance(span, dict) else span)
                    for span in zh_text
                )
            line_count = _zh_line_count(str(zh_text).strip())
            # 英文块 an5 锚点 y = 中文块下缘 + gap（PUTUI 墨迹偏移经验证约相互抵消）。
            y = round(
                height / 2
                + (line_count - 1) * chinese_font_size / 2
                + zh_bottom_offset
                + gap
            )
            en_cues.append({
                "start": cue["start"],
                "end": cue["end"],
                "text": translation,
                "language": "en",
                "position": {"alignment": 5, "x": width // 2, "y": y},
            })
    else:
        en_cues = [
            {"start": cue["start"], "end": cue["end"], "text": translation, "language": "en"}
            for cue, translation in en_pairs
        ]
    secondary = generate_subtitles(
        en_cues,
        cache_root / "timeline-secondary.ass",
        width,
        height,
        style=style,
        position=position,
    )
    return secondary["output_path"]


def _emphasis_lines_ass(
    cues: list[dict],
    settings: dict | None,
    cache_root: Path,
    width: int,
    height: int,
    progress: ProgressCallback | None,
) -> dict | None:
    """重点句大字图层；内容句普通字幕就地让位到底部。失败静默跳过。"""
    if not settings or not cues:
        return None
    try:
        result = generate_emphasis_lines(
            cues,
            cache_root / "emphasis-lines.ass",
            width,
            height,
            settings,
            progress=progress,
        )
    except Exception as exc:  # noqa: BLE001 - 大字层失败不阻断成片
        if progress:
            progress(f"重点句大字层生成失败，已跳过：{exc}")
        return None
    if not result:
        return None
    if progress:
        progress(f"重点句大字层：{len(result['groups'])} 组，{len(result['repositioned'])} 句让位")
    return result


def _sticker_overlays(names: list[str] | tuple[str, ...] | None, cache_root: Path, width: int, height: int) -> list[dict]:
    overlays: list[dict] = []
    for index, name in enumerate(names or ()):
        sticker = str(name or "").strip()
        if not sticker:
            continue
        overlays.append(
            generate_sticker(
                sticker,
                cache_root / f"sticker-{index:02d}-{sticker}.mov",
                width,
                height,
            )
        )
    return overlays


def generate_final_video(
    shots: list[dict],
    output_path: str | Path,
    cache_dir: str | Path,
    *,
    size: str,
    tts_path: str | Path,
    bgm_path: str | Path | None = None,
    cover_path: str | Path | None = None,
    cover_duration: float | None = None,
    stickers: list[str] | tuple[str, ...] | None = None,
    force_shot_ids: list[str] | None = None,
    opening_sfx: list[dict] | None = None,
    bgm_start_seconds: float | None = None,
    bgm_gain: float | None = None,
    subtitle_style: dict | None = None,
    subtitle_position: dict | None = None,
    secondary_subtitles: dict | None = None,
    emphasis_lines: dict | None = None,
    extra_ass_paths: list[str | Path] | None = None,
    normalize_composed: bool = False,
    progress: ProgressCallback | None = None,
) -> dict:
    """先拼无音镜头，再一次叠配音、BGM、字幕、贴纸和封面。"""
    if not isinstance(shots, list) or not shots:
        raise InvalidParameterError("shots", "shots 必须是至少一个镜头")
    cache_root = Path(cache_dir).resolve()
    cache_root.mkdir(parents=True, exist_ok=True)
    destination = Path(output_path).resolve()
    destination.parent.mkdir(parents=True, exist_ok=True)

    if progress:
        progress("正在渲染镜头")
    composed = compose_shots(
        [_compose_item(shot) for shot in shots],
        cache_root / "composed.mp4",
        cache_root / "shots",
        size=size,
        force_shot_ids=force_shot_ids,
        progress=progress,
    )
    body_video_path = composed["output_path"]
    if normalize_composed:
        body_video_path, normalize_cache_hit = _normalize_composed_video(
            composed["output_path"], cache_root / "composed-normalized.mp4"
        )
        if progress:
            progress(
                "已复用规范化镜头缓存"
                if normalize_cache_hit
                else "已完成镜头时间戳规范化"
            )
    width, height = parse_size(size)
    cues = _subtitle_cues(shots, composed["shots"])
    emphasis_result = _emphasis_lines_ass(
        cues, emphasis_lines, cache_root, width, height, progress
    )
    emphasis_path = emphasis_result["output_path"] if emphasis_result else None
    overlays = _sticker_overlays(stickers, cache_root, width, height)
    # 大字驻留期间普通字幕不展示：过滤掉被重点句标记 hidden 的 cue。
    visible_cues = [cue for cue in cues if not cue.get("hidden")]
    ass_path = None
    fontsdir = None
    if visible_cues:
        subtitles = generate_subtitles(
            visible_cues,
            cache_root / "timeline.ass",
            width,
            height,
            style=subtitle_style,
            position=subtitle_position,
        )
        ass_path = subtitles["output_path"]
        fontsdir = subtitles["fontsdir"]
    if progress:
        progress("正在合成配音与字幕")
    extra_ass = list(extra_ass_paths or [])
    if emphasis_path:
        extra_ass.append(emphasis_path)
    opening_sfx_items = list(opening_sfx or [])
    secondary_path = _secondary_subtitle_ass(
        visible_cues, secondary_subtitles or {}, subtitle_style, cache_root, width, height, progress
    )
    if secondary_path:
        extra_ass.append(secondary_path)
    body = mix_body(
        body_video_path,
        destination,
        tts_path=tts_path,
        bgm_path=None if bgm_path is None else (str(bgm_path).strip() or None),
        ass_path=ass_path,
        extra_ass_paths=extra_ass,
        fontsdir=fontsdir,
        overlays=overlays or None,
        cover_path=str(cover_path or "").strip() or None,
        cover_duration=cover_duration,
        opening_sfx=opening_sfx_items,
        bgm_start_seconds=bgm_start_seconds,
        bgm_gain=bgm_gain,
    )
    return {
        "output_path": body["output_path"],
        "duration": body["duration"],
        "body_duration": composed["duration"],
        "shot_count": composed["shot_count"],
    }
