"""以固定单词卡、双语配音生成竖版词汇视频。"""

import json
import shutil
import subprocess
from concurrent.futures import ThreadPoolExecutor, as_completed
from pathlib import Path

from PIL import Image, ImageDraw

from core.tools.cloudflare_data import commit_production_outputs
from core.tools.generate_final_video import generate_final_video, safe_filename
from core.tools.generate_sticker import generate_sticker
from core.tools.generate_tts import generate_tts

from .._constants import (
    CARD_CANVAS_SIZE,
    COUNTDOWN_AUDIO_PATH,
    DEFAULT_VIDEO_FORMATS,
    QUIZ_POST_QUESTION_TRIM_SECONDS,
    SUPPORTED_VIDEO_FORMATS,
    WORDS_PER_TASK,
    WORDS_PER_VIDEO,
    publish_date_from_run_id,
    production_dirs,
    video_content_kind,
    video_production_id,
)
from .._errors import VocabularyVideoError
from .publish_vocabulary_videos import build_video_title, strip_quiz_title_suffix

VIDEO_SIZE = f"{CARD_CANVAS_SIZE[0]}x{CARD_CANVAS_SIZE[1]}"
QUIZ_VIDEO_FPS = 30


def _audio_duration(path: Path) -> float:
    """读取倒计时音轨的实际时长。"""
    ffprobe = shutil.which("ffprobe")
    if not ffprobe:
        raise VocabularyVideoError("找不到 ffprobe，无法读取倒计时音轨时长")
    completed = subprocess.run(
        [
            ffprobe,
            "-v", "error",
            "-show_entries", "format=duration",
            "-of", "default=noprint_wrappers=1:nokey=1",
            str(path),
        ],
        check=False,
        capture_output=True,
        text=True,
        encoding="utf-8",
        errors="replace",
    )
    try:
        duration = float(completed.stdout.strip())
    except (TypeError, ValueError) as exc:
        detail = (completed.stderr or completed.stdout or "").strip()
        raise VocabularyVideoError(f"无法读取倒计时音轨时长：{detail or path}") from exc
    if completed.returncode != 0 or duration <= 0:
        raise VocabularyVideoError(f"倒计时音轨时长无效：{path}")
    return duration


def _concat_wav_files(paths: list[Path], output_path: Path) -> Path:
    """顺序拼接每个词的独立配音，保留各词结尾 0.3 秒停顿。"""
    ffmpeg = shutil.which("ffmpeg")
    if not ffmpeg:
        raise VocabularyVideoError("找不到 ffmpeg，无法拼接问答版配音")
    manifest = output_path.with_suffix(".txt")
    manifest.write_text(
        "".join(f"file '{path.resolve().as_posix()}'\n" for path in paths),
        encoding="utf-8",
    )
    completed = subprocess.run(
        [
            ffmpeg,
            "-y",
            "-f", "concat",
            "-safe", "0",
            "-i", str(manifest),
            "-ac", "1",
            "-ar", "48000",
            "-c:a", "pcm_s16le",
            str(output_path),
        ],
        check=False,
        capture_output=True,
        text=True,
        encoding="utf-8",
        errors="replace",
    )
    manifest.unlink(missing_ok=True)
    if completed.returncode != 0 or not output_path.is_file():
        detail = (completed.stderr or completed.stdout or "").strip()[-1500:]
        raise VocabularyVideoError(f"问答版配音拼接失败：{detail or '未知错误'}")
    return output_path


def _build_hidden_quiz_card(card: Path, output_dir: Path, identifier: str) -> Path:
    """生成只保留主体图、隐藏下方答案文字的提问卡。"""
    output_dir.mkdir(parents=True, exist_ok=True)
    try:
        with Image.open(card) as source:
            image = source.convert("RGB")
    except Exception as exc:
        raise VocabularyVideoError(f"无法读取问答版卡片：{card}") from exc
    background = image.getpixel((20, 20))
    ImageDraw.Draw(image).rectangle((0, 985, image.width, image.height), fill=background)
    path = output_dir / f"{identifier}-question.png"
    image.save(path, format="PNG", optimize=True)
    return path


def _render_countdown_segment(hidden_card: Path, sticker: dict, output_path: Path) -> Path:
    """把 sticker 工具生成的透明倒计时素材叠到提问卡答案区域。"""
    ffmpeg = shutil.which("ffmpeg")
    if not ffmpeg:
        raise VocabularyVideoError("找不到 ffmpeg，无法合成倒计时贴纸镜头")
    output_path.parent.mkdir(parents=True, exist_ok=True)
    duration = float(sticker["duration"])
    completed = subprocess.run(
        [
            ffmpeg, "-y",
            "-loop", "1", "-framerate", str(QUIZ_VIDEO_FPS),
            "-t", f"{duration:.9f}", "-i", str(hidden_card),
            "-i", str(sticker["output_path"]),
            "-filter_complex",
            f"[0:v][1:v]overlay=x={int(sticker['x'])}:y={int(sticker['y'])}:format=auto:eof_action=endall[v]",
            "-map", "[v]", "-an", "-r", str(QUIZ_VIDEO_FPS),
            "-c:v", "libx264", "-preset", "veryfast", "-crf", "21",
            "-tune", "stillimage", "-pix_fmt", "yuv420p",
            "-movflags", "+faststart", str(output_path),
        ],
        check=False,
        capture_output=True,
        text=True,
        encoding="utf-8",
        errors="replace",
    )
    if completed.returncode != 0 or not output_path.is_file():
        detail = (completed.stderr or completed.stdout or "").strip()[-2000:]
        raise VocabularyVideoError(f"倒计时贴纸镜头合成失败：{detail or '未知错误'}")
    return output_path


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
        "video_format": "standard",
        "learning_mode": mode,
        "output_paths": [item["output_path"] for item in outputs],
        "video_parts": outputs,
        "duration": round(cursor, 3),
        "word_count": len(rows),
        "timeline": timeline,
    }


def _one_quiz_mode(
    mode: str,
    card_dir: Path,
    words: list[dict],
    cache_root: Path,
    output_root: Path,
    topic: str,
    word_pause: float,
    voices: dict[str, str],
    question_voices: dict[str, str],
    countdown_audio_path: Path,
) -> dict:
    """生成整期十个词的看图倒计时问答版。"""
    rows, cards = _items(words), _load_cards(card_dir, words)
    target_key = "chinese" if mode == "en-zh" else "korean"
    target_voice = str(voices.get("zh" if mode == "en-zh" else "ko") or "").strip()
    question_voice = str(question_voices.get("zh" if mode == "en-zh" else "ko") or "").strip()
    question_text = "这是什么？" if mode == "en-zh" else "이게 뭐예요?"
    if not target_voice or not question_voice:
        raise VocabularyVideoError("问答版 voices 与 question_voices 必须包含目标语言音色（zh 或 ko）")
    if not countdown_audio_path.is_file():
        raise VocabularyVideoError(f"倒计时音轨不存在：{countdown_audio_path}")
    countdown_duration = _audio_duration(countdown_audio_path)

    segment_dir = cache_root / "quiz"
    segment_dir.mkdir(parents=True, exist_ok=True)
    countdown_sticker = generate_sticker(
        "countdown",
        segment_dir / "countdown.mov",
        CARD_CANVAS_SIZE[0],
        CARD_CANVAS_SIZE[1],
        duration=countdown_duration,
    )
    countdown_video_duration = float(countdown_sticker["duration"])

    def _one_word_tts(index: int, word: dict) -> dict:
        return generate_tts(
            [
                {"text": question_text, "voice": question_voice, "rate": "+0%"},
                {"text": word[target_key], "voice": target_voice},
            ],
            segment_dir / "tts" / f"w{index:02d}" / "narration.wav",
            pause_between=countdown_video_duration,
            pause_end=word_pause,
        )

    word_tts: list[dict | None] = [None] * len(rows)
    try:
        with ThreadPoolExecutor(max_workers=min(3, len(rows))) as executor:
            futures = {
                executor.submit(_one_word_tts, index, word): index - 1
                for index, word in enumerate(rows, 1)
            }
            for future in as_completed(futures):
                word_tts[futures[future]] = future.result()
    except Exception as exc:
        raise VocabularyVideoError(f"问答版配音失败：{exc}") from exc
    if any(item is None for item in word_tts):
        raise VocabularyVideoError("问答版存在未完成的单词配音")
    narration_path = _concat_wav_files(
        [Path(item["output_path"]) for item in word_tts if item is not None],
        segment_dir / "narration.wav",
    )

    shots: list[dict] = []
    countdown_audio_cues: list[dict] = []
    timeline: list[dict] = []
    cursor = 0.0
    quiz_card_dir = segment_dir / "cards"
    for index, (word, card) in enumerate(zip(rows, cards), 1):
        cues = word_tts[index - 1]["timeline"]
        if len(cues) != 2:
            raise VocabularyVideoError(f"第 {index} 个词的问答配音时间轴必须正好有 2 条")
        question_cue, answer_cue = cues
        question_duration = float(question_cue["duration"])
        answer_duration = float(answer_cue["duration"])
        original_prompt_duration = max(0.05, question_duration - countdown_video_duration)
        shortened_pause = min(
            QUIZ_POST_QUESTION_TRIM_SECONDS,
            max(0.0, original_prompt_duration - 0.05),
        )
        prompt_duration = original_prompt_duration - shortened_pause
        answer_duration += shortened_pause
        hidden_card = _build_hidden_quiz_card(card, quiz_card_dir, f"w{index:02d}")
        shots.append({
            "id": f"w{index:02d}-question",
            "image_path": str(hidden_card),
            "duration": prompt_duration,
        })
        countdown_segment = _render_countdown_segment(
            hidden_card,
            countdown_sticker,
            segment_dir / "countdown-segments" / f"w{index:02d}.mp4",
        )
        countdown_audio_cues.append({
            "path": str(countdown_audio_path),
            "start": cursor + prompt_duration,
            "duration": countdown_duration,
            "gain": 1.0,
        })
        shots.append({
            "id": f"w{index:02d}-countdown",
            "segment_path": str(countdown_segment),
        })
        shots.append({
            "id": f"w{index:02d}-answer",
            "image_path": str(card),
            "duration": answer_duration,
        })
        word_duration = prompt_duration + countdown_video_duration + answer_duration
        timeline.append({
            **word,
            "start": round(cursor, 3),
            "countdown_start": round(cursor + prompt_duration, 3),
            "answer_start": round(cursor + prompt_duration + countdown_video_duration, 3),
            "answer_display_extension": round(shortened_pause, 3),
            "end": round(cursor + word_duration, 3),
            "duration": round(word_duration, 3),
        })
        cursor += word_duration

    title = strip_quiz_title_suffix(build_video_title(mode, topic, rows))
    try:
        video = generate_final_video(
            shots,
            output_root / f"{safe_filename(title)}.mp4",
            segment_dir / "final-cache",
            size=VIDEO_SIZE,
            tts_path=narration_path,
            opening_sfx=countdown_audio_cues,
        )
    except Exception as exc:
        raise VocabularyVideoError(f"问答版拼接失败：{exc}") from exc
    (segment_dir / "timeline.json").write_text(
        json.dumps(timeline, ensure_ascii=False, indent=2),
        encoding="utf-8",
    )
    part = {
        "part": 1,
        "output_path": video["output_path"],
        "title": title,
        "word_start": 1,
        "word_end": len(rows),
        "duration": round(video["duration"], 3),
    }
    return {
        "video_format": "quiz",
        "learning_mode": mode,
        "output_paths": [video["output_path"]],
        "video_parts": [part],
        "duration": round(video["duration"], 3),
        "word_count": len(rows),
        "timeline": timeline,
        "countdown_audio_path": str(countdown_audio_path),
        "countdown_duration": round(countdown_duration, 6),
        "countdown_video_duration": round(countdown_video_duration, 6),
    }


def create_vocabulary_videos(
    card_dirs: dict[str, str],
    words_by_mode: dict,
    run_id: str,
    topic: str = "",
    language_pause: float = 0.3,
    word_pause: float = 0.3,
    production_source: str = "local_mcp",
    video_formats: list[str] | None = None,
    countdown_audio_path: str | None = None,
    record_production_outputs: bool = True,
    *,
    voices: dict[str, str],
    question_voices: dict[str, str] | None = None,
    hashtags_by_mode: dict[str, list[str]] | None = None,
    progress=None,
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
    formats = list(dict.fromkeys(video_formats or list(DEFAULT_VIDEO_FORMATS)))
    unsupported_formats = [item for item in formats if item not in SUPPORTED_VIDEO_FORMATS]
    if unsupported_formats:
        raise VocabularyVideoError(f"video_formats 包含不支持的格式：{unsupported_formats}")
    resolved_countdown_audio = None
    if "quiz" in formats:
        resolved_countdown_audio = Path(str(countdown_audio_path or COUNTDOWN_AUDIO_PATH)).resolve()
        if not resolved_countdown_audio.is_file():
            raise VocabularyVideoError(
                "生成 quiz 问答版需要倒计时音轨。"
                f"默认文件不存在：{COUNTDOWN_AUDIO_PATH}。请传入有效的 countdown_audio_path"
            )
    cache_root, output_root = production_dirs(run_id)
    output_root.mkdir(parents=True, exist_ok=True)
    results_by_key: dict[tuple[str, str], dict] = {}
    configured_question_voices = question_voices or voices
    total_jobs = sum(1 for mode in modes if "standard" in formats) + sum(
        1 for mode in modes if "quiz" in formats and resolved_countdown_audio is not None
    )
    if progress is not None:
        progress(f"开始出片：{modes} × {formats}，共 {total_jobs} 条")
    with ThreadPoolExecutor(max_workers=len(modes) * len(formats)) as executor:
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
            ): (mode, "standard")
            for mode in modes
            if "standard" in formats
        }
        futures.update({
            executor.submit(
                _one_quiz_mode,
                mode,
                Path(card_dirs[mode]).resolve(),
                words_by_mode.get(mode) or [],
                cache_root / mode,
                output_root,
                str(topic).strip(),
                word_pause,
                voices,
                configured_question_voices,
                resolved_countdown_audio,
            ): (mode, "quiz")
            for mode in modes
            if "quiz" in formats and resolved_countdown_audio is not None
        })
        for future in as_completed(futures):
            mode, video_format = futures[future]
            results_by_key[(mode, video_format)] = future.result()
            if progress is not None:
                progress(
                    f"已完成出片 {mode}/{video_format}（{len(results_by_key)}/{len(futures)}）"
                )
    results = [
        results_by_key[(mode, video_format)]
        for mode in modes
        for video_format in formats
    ]
    publish_date = publish_date_from_run_id(run_id)
    payload = {
        "topic": str(topic).strip(),
        "run_id": run_id,
        "publish_date": publish_date,
        "production_source": production_source,
        "cache_dir": str(cache_root),
        "output_dir": str(output_root),
        "learning_modes": modes,
        "video_formats": formats,
        "record_production_outputs": bool(record_production_outputs),
        "language_pause": language_pause,
        "word_pause": word_pause,
        "videos": results,
    }
    if production_source == "local_mcp" and record_production_outputs:
        configured_hashtags = hashtags_by_mode or {}
        payload["production_outputs"] = commit_production_outputs([
            {
                "production_id": video_production_id(
                    "local_mcp",
                    run_id,
                    video["learning_mode"],
                    video["video_format"],
                    part["part"],
                ),
                "run_id": run_id,
                "publish_date": publish_date,
                "business_line": "language_learning",
                "content_kind": video_content_kind(video["learning_mode"], video["video_format"]),
                "content_part": part["part"],
                "title": part["title"],
                "hashtags": " ".join(
                    f"#{str(tag).strip().lstrip('#')}"
                    for tag in configured_hashtags.get(video["learning_mode"], [])
                    if str(tag).strip().lstrip("#")
                ),
                "source": "local_mcp",
                "local_path": part["output_path"],
                "r2_url": None,
                "r2_expires_at": None,
            }
            for video in results
            for part in video["video_parts"]
        ])
    return payload
