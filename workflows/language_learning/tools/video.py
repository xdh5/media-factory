"""以固定单词卡、双语配音生成竖版词汇视频。"""

import json
from pathlib import Path

from core.tools.tts import generate_tts
from core.tools.video import generate_video

from .._constants import (
    CARD_CANVAS_SIZE,
    DEFAULT_LANGUAGE_PAUSE,
    DEFAULT_WORD_PAUSE,
    VOICE_BY_LANGUAGE,
    WORDS_PER_TASK,
    WORDS_PER_VIDEO,
    production_dirs,
)
from .._errors import VocabularyVideoError
from .filenames import safe_filename
from .publish import build_video_title

VIDEO_SIZE = f"{CARD_CANVAS_SIZE[0]}x{CARD_CANVAS_SIZE[1]}"


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
    shots = []
    timeline = []
    cursor = 0.0
    for index, (word, card) in enumerate(zip(rows, cards), 1):
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
        duration = float(tts["total_duration"])
        shots.append({
            "id": f"w{index:02d}",
            "image_path": str(card),
            "audio_path": str(audio_path),
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
        try:
            video = generate_video(
                part_shots,
                size=VIDEO_SIZE,
                cache_dir=cache_root / "video-cache" / f"part-{part}",
                output_dir=output_root,
                title=title,
            )
        except Exception as exc:
            raise VocabularyVideoError(f"第 {part} 段出片失败：{exc}") from exc
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
    results = [
        _one_mode(
            mode,
            Path(card_dirs[mode]).resolve(),
            words_by_mode.get(mode) or [],
            cache_root / mode,
            output_root,
            str(topic).strip(),
            language_pause,
            word_pause,
        )
        for mode in modes
    ]
    return {
        "topic": str(topic).strip(),
        "run_id": run_id,
        "cache_dir": str(cache_root),
        "output_dir": str(output_root),
        "learning_modes": modes,
        "language_pause": language_pause,
        "word_pause": word_pause,
        "videos": results,
    }
