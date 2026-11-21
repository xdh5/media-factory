"""转写开头片段，准备并保存分段封面。"""

from __future__ import annotations

import json
import subprocess
from io import BytesIO
from pathlib import Path

from .._constants import SEGMENTATION_DURATION
from .._errors import AnimeError
from .ffmpeg import media_executable, subprocess_options
from .media_artifacts import file_sha256, write_json, load_manifest
from .segmentation import part_ranges, split_ranges
from .youtube_metadata import part_title


def transcribe_intros(manifest_path: str, progress=None) -> dict:
    """只抽取第一段从零秒开始的前一分钟，缓存原始转写。"""
    from tools.transcribe import transcribe

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


_THUMBNAIL_MAX_BYTES = 2 * 1024 * 1024


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
    from PIL import Image, ImageOps

    with Image.open(source) as image:
        rgb = ImageOps.fit(image.convert("RGB"), (1280, 720))
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
    """提取画风参考帧，返回各段所需标题，供宿主直接生成封面。"""
    directory, parts = load_manifest(manifest_path)
    if len(titles) != 1 or not titles[0].strip():
        raise AnimeError("需要一个共用封面标题")
    count = len(parts)
    selection_path = directory / "selection.json"
    if selection_path.is_file():
        selection = json.loads(selection_path.read_text(encoding="utf-8"))
        durations = [float(item["duration_seconds"]) for item in selection.get("sources") or []]
        if durations and sum(durations) > 0:
            count = (len(split_ranges(sum(durations))) if selection.get("segmentation") == SEGMENTATION_DURATION
                     else len(part_ranges(durations)))
    frame = directory / "youtube-style-frame.jpg"
    sample = parts[0]
    _extract_style_frame(Path(sample["video_path"]), frame, float(sample["duration_seconds"]))
    return {
        "reference_image_path": str(frame.resolve()),
        "thumbnails": [{"part_index": index, "title": part_title(titles[0], index, count)}
                       for index in range(1, count + 1)],
    }


def save_youtube_thumbnails(manifest_path: str, titles: list[str], images: list[dict]) -> dict:
    """接收宿主生成的图片路径，保存为 YouTube 可上传的 JPEG。"""
    directory, parts = load_manifest(manifest_path)
    reference = prepare_youtube_thumbnails(manifest_path, titles)
    provided = {int(item["part_index"]): Path(item["image_path"]).resolve() for item in images}
    expected = {item["part_index"] for item in reference["thumbnails"]}
    if set(provided) != expected or len(images) != len(expected):
        raise AnimeError("封面图片必须完整对应每个分段，且不能重复")
    digest = file_sha256(Path(parts[0]["video_path"]))
    saved = []
    for item in reference["thumbnails"]:
        index = item["part_index"]
        thumbnail = directory / f"youtube-thumbnail-{index}.jpg"
        _jpeg_under_limit(provided[index], thumbnail)
        write_json(thumbnail.with_suffix(".json"), {"title": item["title"], "video_sha256": digest})
        saved.append({"part_index": index, "thumbnail_path": str(thumbnail.resolve())})
    return {"thumbnails": saved}


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
