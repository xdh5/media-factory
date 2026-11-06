"""转写开头片段，准备并保存分段封面。"""

from __future__ import annotations

import json
import subprocess
from io import BytesIO
from pathlib import Path

from .._constants import SEGMENTATION_DURATION
from .._errors import AnimeError
from .ffmpeg import media_executable, subprocess_options
from .media_artifacts import file_sha256, resolve_output_path, write_json, load_manifest
from .segmentation import part_ranges, split_ranges
from .youtube_metadata import part_title


def transcribe_intros(manifest_path: str, progress=None) -> dict:
    """只抽取第一段从零秒开始的前一分钟，缓存原始转写。"""
    from core.tools.transcribe import transcribe

    directory, parts = load_manifest(manifest_path)
    results = []
    for part in parts[:1]:
        index = part["part_index"]
        transcript = directory / f"youtube-intro-{index}.json"
        if not transcript.is_file():
            if progress:
                progress(f"正在转写第 {index} 段前一分钟")
            clip = directory / f"youtube-intro-{index}.mp3"
            subprocess.run([
                media_executable("ffmpeg"), "-v", "error", "-y", "-i", part["video_path"],
                "-t", "60", "-vn", "-ac", "1", str(clip),
            ], check=True, capture_output=True, timeout=120, **subprocess_options())
            write_json(transcript, transcribe(clip))
        results.append({"part_index": index, "original_title": part.get("title"),
                        "transcript": json.loads(transcript.read_text(encoding="utf-8"))})
    return {"manifest_path": manifest_path, "intros": results}


_THUMBNAIL_SIZE = "1280x720"
_THUMBNAIL_MAX_BYTES = 2 * 1024 * 1024


def _thumbnail_prompt(title: str) -> str:
    """一次生成同时包含画面和标题，不接受先出图再叠字。"""
    return (
        "一次生成一张 16:9 YouTube 封面。画面和标题必须在同一次出图里一起完成，"
        "禁止先生成无字图片，再后期贴字、叠字或另外加文字图层。"
        "画风、线条、上色和角色造型语言与参考帧一致，不要改成写实照片或其他画风。"
        "把下面的标题原文作为画面的一部分完整、清晰地画在画面正中间，不要放在顶部或底部，不要改字、漏字，也不要添加标题以外的文字：\n"
        f"{title}"
    )


def _extract_style_frame(video: Path, destination: Path, duration: float) -> None:
    """抽取成片中段附近的一帧，作为封面画风参考。"""
    offset = 8.0 if duration > 12 else max(0.2, duration / 2)
    completed = subprocess.run([
        media_executable("ffmpeg"), "-v", "error", "-y", "-ss", f"{offset:.3f}", "-i", str(video),
        "-frames:v", "1", "-q:v", "2", str(destination),
    ], check=False, capture_output=True, timeout=120, **subprocess_options())
    if completed.returncode != 0 or not destination.is_file():
        detail = (completed.stderr or b"").decode("utf-8", errors="replace").strip()[-500:]
        raise AnimeError("抽取视频画风参考帧失败", {"stderr": detail})


def _jpeg_under_limit(source: Path, destination: Path) -> None:
    """压成 YouTube 封面要求的 2MB 以内 JPEG。"""
    from PIL import Image

    with Image.open(source) as image:
        rgb = image.convert("RGB")
        quality = 90
        while True:
            buffer = BytesIO()
            rgb.save(buffer, format="JPEG", quality=quality, optimize=True)
            if buffer.tell() <= _THUMBNAIL_MAX_BYTES or quality <= 50:
                destination.write_bytes(buffer.getvalue())
                break
            quality -= 8
    if destination.stat().st_size > _THUMBNAIL_MAX_BYTES:
        raise AnimeError("YouTube 封面超过 2MB")


def prepare_youtube_thumbnails(manifest_path: str, titles: list[str]) -> dict:
    """只抽一帧画风参考，按预计分段数分别生成带集数标题的封面任务。"""
    from core.tools.generate_image import ImageGenerationError, prepare_agent_image_tasks

    directory, parts = load_manifest(manifest_path)
    if len(titles) != 1:
        raise AnimeError("只需提供一个共用封面标题")
    if any(not str(title).strip() for title in titles):
        raise AnimeError("封面标题不能为空")
    selection_path = directory / "selection.json"
    expected_part_count = len(parts)
    if selection_path.is_file():
        selection = json.loads(selection_path.read_text(encoding="utf-8"))
        durations = [float(item["duration_seconds"]) for item in selection.get("sources") or []]
        if durations and sum(durations) > 0:
            if selection.get("segmentation") == SEGMENTATION_DURATION:
                expected_part_count = len(split_ranges(sum(durations)))
            else:
                expected_part_count = len(part_ranges(durations))
    prepared_tasks = []
    titles_by_image_id = {}
    digests = {}
    version = None
    frame = directory / "youtube-style-frame.jpg"
    sample = parts[0]
    _extract_style_frame(Path(sample["video_path"]), frame, float(sample["duration_seconds"]))
    preview_digest = file_sha256(Path(sample["video_path"]))
    for index in range(1, expected_part_count + 1):
        image_id = f"youtube-thumbnail-{index}"
        text = part_title(titles[0], index, expected_part_count)
        titles_by_image_id[image_id] = text
        digests[image_id] = preview_digest
        try:
            one = prepare_agent_image_tasks(
                [{"image_id": image_id, "kind": "youtube-thumbnail", "prompt": _thumbnail_prompt(text)}],
                None,
                "16:9",
                _THUMBNAIL_SIZE,
                directory,
                additional_reference_image_paths=[frame],
                context_path=directory / f".{image_id}-context.json",
                reference_usage="style_only",
            )
        except ImageGenerationError as exc:
            raise AnimeError(exc.message, exc.details) from exc
        version = one["version"]
        for task in one["tasks"]:
            task["reference_failure_policy"] = (
                "宿主先查看这一张参考帧，再一次生成封面。画风以这张参考帧为准。"
                "标题必须和画面在同一次出图里一起生成，并且放在画面正中间，禁止先出无字图再叠字。"
                "不要调用千问或其他生图接口代替宿主。"
            )
        prepared_tasks.extend(one["tasks"])
    context_path = directory / "youtube-thumbnail-context.json"
    context = {
        "version": version,
        "status": "awaiting_agent_images",
        "tasks": prepared_tasks,
        "metadata": {
            "workflow": "anime-youtube-thumbnail",
            "titles_by_image_id": titles_by_image_id,
            "video_sha256_by_image_id": digests,
        },
        "context_path": context_path.resolve().as_posix(),
    }
    context_path.write_text(json.dumps(context, ensure_ascii=False, indent=2), encoding="utf-8")
    return context


def save_youtube_thumbnails(context_path: str, images: list[dict]) -> dict:
    """保存宿主生成的封面，并压成 YouTube 可上传的 JPEG。"""
    from core.tools.generate_image import ImageGenerationError, save_agent_image_tasks

    resolved = resolve_output_path(context_path)
    if resolved.name != "youtube-thumbnail-context.json":
        raise AnimeError("必须传 prepare 返回的 youtube-thumbnail-context.json")
    try:
        context = json.loads(resolved.read_text(encoding="utf-8"))
    except (OSError, json.JSONDecodeError) as exc:
        raise AnimeError(f"读取封面任务失败：{exc}") from exc
    tasks = context.get("tasks") or []
    if images:
        try:
            save_agent_image_tasks(resolved, images)
        except ImageGenerationError as exc:
            raise AnimeError(exc.message, exc.details) from exc
    titles = (context.get("metadata") or {}).get("titles_by_image_id") or {}
    digests = (context.get("metadata") or {}).get("video_sha256_by_image_id") or {}
    saved = []
    for task in tasks:
        image_id = str(task["image_id"])
        png = Path(task["output_path"])
        if not png.is_file():
            raise AnimeError(f"封面 {image_id} 尚未由宿主生成")
        thumbnail = png.with_suffix(".jpg")
        _jpeg_under_limit(png, thumbnail)
        write_json(thumbnail.with_suffix(".json"), {"title": titles.get(image_id), "video_sha256": digests.get(image_id)})
        saved.append({"image_id": image_id, "thumbnail_path": thumbnail.resolve().as_posix()})
    return {"context_path": resolved.resolve().as_posix(), "thumbnails": saved}


def require_host_thumbnail(directory: Path, index: int, title: str, digest: str) -> Path:
    """发布只接收宿主已经按当前标题生成的封面。"""
    thumbnail = directory / f"youtube-thumbnail-{index}.jpg"
    metadata_path = directory / f"youtube-thumbnail-{index}.json"
    if not thumbnail.is_file() or not metadata_path.is_file():
        raise AnimeError("请先由宿主根据成片画风生成带标题的 YouTube 封面")
    try:
        saved = json.loads(metadata_path.read_text(encoding="utf-8"))
    except json.JSONDecodeError as exc:
        raise AnimeError("YouTube 封面记录无法读取") from exc
    if saved.get("title") != title or saved.get("video_sha256") != digest:
        raise AnimeError("封面与本次成片或标题不一致，请由宿主重新生成")
    return thumbnail
