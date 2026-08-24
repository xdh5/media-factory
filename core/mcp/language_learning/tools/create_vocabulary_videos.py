"""以固定单词卡、双语配音生成竖版词汇视频。"""

import json
from concurrent.futures import ThreadPoolExecutor, as_completed
from pathlib import Path

from core.tools.cloudflare_data import commit_production_outputs
from core.tools.generate_final_video import generate_final_video, safe_filename
from core.tools.generate_tts import generate_tts

from .._constants import (
    CARD_CANVAS_SIZE,
    WORDS_PER_TASK,
    WORDS_PER_VIDEO,
    publish_date_from_run_id,
    production_dirs,
)
from .._errors import VocabularyVideoError
from .publish_vocabulary_videos import build_video_title

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
        except Exception as exc:
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
    voices: dict[str, str],
) -> dict:
    rows, cards = _items(words), _load_cards(card_dir, words)
    target_key = "chinese" if mode == "en-zh" else "korean"
    english_voice = str(voices.get("en") or "").strip()
    target_voice = str(voices.get("zh" if mode == "en-zh" else "ko") or "").strip()
    if not english_voice or not target_voice:
        raise VocabularyVideoError("voices 必须包含 en 与目标语言音色（zh 或 ko）")

    outputs = []
    timeline = []
    cursor = 0.0
    part_count = (len(rows) + WORDS_PER_VIDEO - 1) // WORDS_PER_VIDEO
    for part, start in enumerate(range(0, len(rows), WORDS_PER_VIDEO), 1):
        part_words = rows[start:start + WORDS_PER_VIDEO]
        part_cards = cards[start:start + WORDS_PER_VIDEO]
        title = build_video_title(mode, topic, part_words, part=part, part_count=part_count)
        segment_dir = cache_root / "segments" / f"part-{part}"
        segment_dir.mkdir(parents=True, exist_ok=True)
        script = []
        for word in part_words:
            script.append({"text": word["english"], "voice": english_voice})
            script.append({"text": word[target_key], "voice": target_voice})
        try:
            tts = generate_tts(
                script,
                segment_dir / "narration.wav",
                pause_between=language_pause,
                pause_end=word_pause,
            )
        except Exception as extra:
            raise VocabularyVideoError(f"第 {part} 段配音失败：{extra}") from extra
        cues = tts["timeline"]
        if len(cues) != len(script):
            raise VocabularyVideoError(
                f"第 {part} 段配音时间轴条数是 {len(cues)}，期望 {len(script)}"
            )
        part_shots = []
        for offset, (word, card) in enumerate(zip(part_words, part_cards)):
            english_cue = cues[offset * 2]
            target_cue = cues[offset * 2 + 1]
            duration = float(target_cue["end"]) - float(english_cue["start"])
            if duration <= 0:
                raise VocabularyVideoError(f"第 {start + offset + 1} 个单词配音时长无效")
            part_shots.append({
                "id": f"w{start + offset + 1:02d}",
                "image_path": str(card),
                "duration": duration,
            })
            timeline.append({
                **word,
                "start": round(cursor, 3),
                "end": round(cursor + duration, 3),
                "duration": round(duration, 3),
            })
            cursor += duration

        try:
            video = generate_final_video(
                part_shots,
                output_root / f"{safe_filename(title)}.mp4",
                segment_dir / "final-cache",
                size=VIDEO_SIZE,
                tts_path=tts["output_path"],
            )
        except Exception as extra:
            raise VocabularyVideoError(f"第 {part} 段拼接失败：{extra}") from extra
        outputs.append({
            "part": part,
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
    language_pause: float = 0.3,
    word_pause: float = 0.3,
    production_source: str = "local_mcp",
    *,
    voices: dict[str, str],
) -> dict:
    try:
        language_pause, word_pause = max(0.0, float(language_pause)), max(0.0, float(word_pause))
    except (TypeError, ValueError) as exc:
        raise VocabularyVideoError("停顿时长必须是非负数字") from exc
    modes = [mode for mode in ("en-zh", "en-ko") if mode in card_dirs]
    if not modes:
        raise VocabularyVideoError("card_dirs 至少需要一个受支持的语言方向，值为卡片文件夹路径")
    if production_source not in {"local_mcp", "github_workflow"}:
        raise VocabularyVideoError("production_source 必须是 local_mcp 或 github_workflow")
    cache_root, output_root = production_dirs(run_id)
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
                voices,
            ): mode
            for mode in modes
        }
        for future in as_completed(futures):
            results_by_mode[futures[future]] = future.result()
    results = [results_by_mode[mode] for mode in modes]
    publish_date = publish_date_from_run_id(run_id)
    payload = {
        "topic": str(topic).strip(),
        "run_id": run_id,
        "publish_date": publish_date,
        "production_source": production_source,
        "cache_dir": str(cache_root),
        "output_dir": str(output_root),
        "learning_modes": modes,
        "language_pause": language_pause,
        "word_pause": word_pause,
        "videos": results,
    }
    if production_source == "local_mcp":
        payload["production_outputs"] = commit_production_outputs([
            {
                "production_id": f"local_mcp:language_learning:{run_id}:{video['learning_mode']}:{part['part']}",
                "run_id": run_id,
                "publish_date": publish_date,
                "business_line": "language_learning",
                "content_kind": video["learning_mode"],
                "content_part": part["part"],
                "title": part["title"],
                "source": "local_mcp",
                "local_path": part["output_path"],
                "r2_url": None,
            }
            for video in results
            for part in video["video_parts"]
        ])
    return payload
