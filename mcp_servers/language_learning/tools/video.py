"""以固定单词卡、双语配音生成竖版词汇视频。"""

import json
import os
import shutil
from concurrent.futures import ThreadPoolExecutor, as_completed
from pathlib import Path

from core.tools.tts import generate_tts
from core.tools.video import concat_videos, render_shot

from .._constants import (
    CARD_CANVAS_SIZE,
    DEFAULT_LANGUAGE_PAUSE,
    DEFAULT_WORD_PAUSE,
    VIDEO_TTS_WORKERS,
    VOICE_BY_LANGUAGE,
    WORDS_PER_TASK,
    WORDS_PER_VIDEO,
    production_dirs,
)
from .._errors import VocabularyVideoError
from .filenames import safe_filename
from .publish import build_video_title

VIDEO_SIZE = f"{CARD_CANVAS_SIZE[0]}x{CARD_CANVAS_SIZE[1]}"
VIDEO_SHOT_WORKERS = 4


def _user_desktop() -> Path:
    """解析当前用户桌面目录（含 OneDrive 重定向）。"""
    if os.name == "nt":
        try:
            import ctypes

            buffer = ctypes.create_unicode_buffer(260)
            status = ctypes.windll.shell32.SHGetFolderPathW(None, 0x0010, None, 0, buffer)
            if status == 0:
                path = Path(buffer.value)
                if path.is_dir():
                    return path
        except Exception:
            pass
    for candidate in (Path.home() / "Desktop", Path.home() / "桌面"):
        if candidate.is_dir():
            return candidate
    raise VocabularyVideoError("找不到桌面文件夹，无法拷贝成片。请确认当前用户有 Desktop 或「桌面」目录")


def _copy_outputs_to_desktop(results: list[dict]) -> list[str]:
    """中文、韩语成片都拷到桌面；文件名冲突时加上语言方向后缀。"""
    desktop = _user_desktop()
    copies = []
    used_names: set[str] = set()
    for video in results:
        mode = str(video.get("learning_mode") or "video").strip() or "video"
        for path_text in video.get("output_paths") or []:
            source = Path(path_text).resolve()
            if not source.is_file():
                raise VocabularyVideoError(f"成片不存在，无法拷到桌面：{source}")
            dest_name = source.name
            if dest_name in used_names:
                dest_name = f"{source.stem}-{mode}{source.suffix}"
            used_names.add(dest_name)
            destination = desktop / dest_name
            shutil.copy2(source, destination)
            copies.append(str(destination))
    return copies


def _items(words: list[dict]) -> list[dict]:
    if len(words) != WORDS_PER_TASK:
        raise VocabularyVideoError(f"单词数据必须有 {WORDS_PER_TASK} 条，现在是 {len(words)} 条")
    result = []
    for index, item in enumerate(words, 1):
        row = {key: str(item.get(key) or "").strip() for key in ("english", "chinese", "korean", "romanization")}
        if not all(row.values()):
            raise VocabularyVideoError(f"第 {index} 条单词缺少英语、中文、目标语言或发音")
        result.append(row)
    return result


def _load_cards(card_dir: Path, words: list[dict]) -> list[Path]:
    if card_dir.suffix.lower() == ".zip" or card_dir.is_file():
        raise VocabularyVideoError(f"card_dirs 必须指向卡片文件夹，不要再传 zip：{card_dir}")
    if not card_dir.is_dir():
        raise VocabularyVideoError(f"卡片文件夹不存在：{card_dir}")
    paths = []
    for index, word in enumerate(words, 1):
        try:
            path = card_dir / f"{safe_filename(word['english'])}.png"
        except ValueError as exc:
            raise VocabularyVideoError(str(exc)) from exc
        if not path.is_file():
            raise VocabularyVideoError(f"第 {index} 张卡片不存在，文件名必须是单词标题：{path}")
        paths.append(path)
    if len(paths) != WORDS_PER_TASK:
        raise VocabularyVideoError(f"卡片文件夹必须包含 {WORDS_PER_TASK} 张 PNG，实际为 {len(paths)} 张：{card_dir}")
    return paths


def _one_mode(
    mode: str,
    card_dir: Path,
    words: list[dict],
    cache_root: Path,
    output_root: Path,
    topic: str,
    language_pause: float,
    word_pause: float,
) -> dict:
    rows, cards = _items(words), _load_cards(card_dir, words)
    audio_root = cache_root / "audio"
    audio_root.mkdir(parents=True, exist_ok=True)
    target_key = "chinese" if mode == "en-zh" else "korean"
    target_voice = VOICE_BY_LANGUAGE["zh" if mode == "en-zh" else "ko"]

    def _tts_one(index: int, word: dict) -> tuple[int, dict]:
        audio_path = audio_root / f"{index:02d}.wav"
        try:
            tts = generate_tts(
                [
                    {"text": word["english"], "voice": VOICE_BY_LANGUAGE["en"]},
                    {"text": word[target_key], "voice": target_voice},
                ],
                audio_path,
                pause_between=language_pause,
                pause_end=word_pause,
            )
        except Exception as exc:
            raise VocabularyVideoError(f"第 {index} 条配音失败：{exc}") from exc
        return index, tts

    tts_by_index: dict[int, dict] = {}
    workers = max(1, min(VIDEO_TTS_WORKERS, len(rows)))
    with ThreadPoolExecutor(max_workers=workers) as executor:
        futures = [
            executor.submit(_tts_one, index, word)
            for index, word in enumerate(rows, 1)
        ]
        for future in as_completed(futures):
            index, tts = future.result()
            tts_by_index[index] = tts

    shots = []
    timeline = []
    cursor = 0.0
    for index, (word, card) in enumerate(zip(rows, cards), 1):
        tts = tts_by_index[index]
        duration = float(tts["total_duration"])
        shots.append({
            "id": f"w{index:02d}",
            "image_path": str(card),
            "audio_path": str(audio_root / f"{index:02d}.wav"),
        })
        timeline.append({
            **word,
            "start": round(cursor, 3),
            "end": round(cursor + duration, 3),
            "duration": round(duration, 3),
        })
        cursor += duration

    outputs = []
    part_count = (len(shots) + WORDS_PER_VIDEO - 1) // WORDS_PER_VIDEO
    for part, start in enumerate(range(0, len(shots), WORDS_PER_VIDEO), 1):
        part_shots = shots[start:start + WORDS_PER_VIDEO]
        part_words = rows[start:start + WORDS_PER_VIDEO]
        title = build_video_title(mode, topic, part_words, part=part, part_count=part_count)
        segment_dir = cache_root / "segments" / f"part-{part}"
        segment_dir.mkdir(parents=True, exist_ok=True)
        indexed_segments: dict[int, Path] = {}

        def _render_word(offset: int, shot: dict) -> tuple[int, Path]:
            segment = segment_dir / f"{shot['id']}.mp4"
            try:
                render_shot(shot["image_path"], segment, size=VIDEO_SIZE, audio_path=shot["audio_path"])
            except Exception as extra:
                raise VocabularyVideoError(f"第 {start + offset + 1} 个单词出片失败：{extra}") from extra
            return offset, segment

        shot_workers = max(1, min(VIDEO_SHOT_WORKERS, len(part_shots)))
        with ThreadPoolExecutor(max_workers=shot_workers) as executor:
            futures = [
                executor.submit(_render_word, offset, shot)
                for offset, shot in enumerate(part_shots)
            ]
            for future in as_completed(futures):
                offset, segment = future.result()
                indexed_segments[offset] = segment
        try:
            video = concat_videos(
                [indexed_segments[offset] for offset in range(len(part_shots))],
                output_root / f"{safe_filename(title)}.mp4",
            )
        except Exception as extra:
            raise VocabularyVideoError(f"第 {part} 段拼接失败：{extra}") from extra
        outputs.append({
            "output_path": video["output_path"],
            "title": title,
            "word_start": start + 1,
            "word_end": min(start + WORDS_PER_VIDEO, len(rows)),
            "duration": round(video["duration"], 3),
        })
    (cache_root / "timeline.json").write_text(json.dumps(timeline, ensure_ascii=False, indent=2), encoding="utf-8")
    return {
        "learning_mode": mode,
        "output_paths": [item["output_path"] for item in outputs],
        "video_parts": outputs,
        "duration": round(cursor, 3),
        "word_count": len(rows),
        "timeline": timeline,
    }


def create_vocabulary_videos(
    card_dirs: dict[str, str],
    words_by_mode: dict,
    run_id: str,
    topic: str = "",
    language_pause: float = DEFAULT_LANGUAGE_PAUSE,
    word_pause: float = DEFAULT_WORD_PAUSE,
) -> dict:
    try:
        language_pause, word_pause = max(0.0, float(language_pause)), max(0.0, float(word_pause))
    except (TypeError, ValueError) as exc:
        raise VocabularyVideoError("停顿时长必须是非负数字") from exc
    modes = [mode for mode in ("en-zh", "en-ko") if mode in card_dirs]
    if not modes:
        raise VocabularyVideoError("card_dirs 至少需要一个受支持的语言方向，值为卡片文件夹路径")
    _run_dir, cache_root, output_root = production_dirs(run_id)
    output_root.mkdir(parents=True, exist_ok=True)
    results_by_mode: dict[str, dict] = {}
    with ThreadPoolExecutor(max_workers=len(modes)) as executor:
        futures = {
            executor.submit(
                _one_mode,
                mode,
                Path(card_dirs[mode]).resolve(),
                words_by_mode.get(mode) or [],
                cache_root / mode,
                output_root,
                str(topic).strip(),
                language_pause,
                word_pause,
            ): mode
            for mode in modes
        }
        for future in as_completed(futures):
            results_by_mode[futures[future]] = future.result()
    results = [results_by_mode[mode] for mode in modes]
    desktop_copies = _copy_outputs_to_desktop(results)
    return {
        "topic": str(topic).strip(),
        "run_id": run_id,
        "cache_dir": str(cache_root),
        "output_dir": str(output_root),
        "desktop_dir": str(_user_desktop()),
        "desktop_copies": desktop_copies,
        "learning_modes": modes,
        "language_pause": language_pause,
        "word_pause": word_pause,
        "videos": results,
    }
