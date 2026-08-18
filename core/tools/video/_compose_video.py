"""使用逐镜头内容指纹缓存合成完整视频。"""

from __future__ import annotations

import hashlib
import json
import os
import re
import shutil
import subprocess
import tempfile
from pathlib import Path

from ._constants import VIDEO_FFMPEG_TIMEOUT_SECONDS, VIDEO_FPS, VIDEO_RENDERER_VERSION
from ._errors import CacheError, FFmpegNotFoundError, InvalidParameterError, RenderError, RenderTimeoutError
from ._render_shot import _probe, _render_shot, _validate_file
from ._select_subtitle import _parse_size


def _hash_file(path: Path) -> dict:
    if not path.is_file():
        return {"path": str(path.resolve()), "missing": True}
    digest = hashlib.sha256()
    with path.open("rb") as source:
        for chunk in iter(lambda: source.read(1024 * 1024), b""):
            digest.update(chunk)
    return {"path": str(path.resolve()), "size": path.stat().st_size, "sha256": digest.hexdigest()}


def _safe_id(value: str) -> str:
    safe = re.sub(r"[^A-Za-z0-9._-]+", "_", value.strip())
    if not safe:
        raise InvalidParameterError("shots[].id", "镜头 id 不能为空")
    return safe[:120]


def _signature(shot: dict, size: str) -> str:
    image = Path(str(shot.get("image_path") or ""))
    audio_value = shot.get("audio_path")
    payload = {
        "renderer_version": VIDEO_RENDERER_VERSION,
        "fps": VIDEO_FPS,
        "size": size,
        "shot": {
            "id": shot.get("id"),
            "duration": shot.get("duration"),
            "audio_start": shot.get("audio_start"),
            "audio_end": shot.get("audio_end"),
            "subtitle": shot.get("subtitle"),
            "subtitle_language": shot.get("subtitle_language", "zh"),
            "motion": shot.get("motion"),
        },
        "image": _hash_file(image),
        "audio": _hash_file(Path(str(audio_value))) if audio_value else None,
    }
    encoded = json.dumps(payload, ensure_ascii=False, sort_keys=True, separators=(",", ":")).encode("utf-8")
    return hashlib.sha256(encoded).hexdigest()


def _valid_cache(video_path: Path, metadata_path: Path, signature: str) -> bool:
    if not video_path.is_file() or not metadata_path.is_file():
        return False
    try:
        metadata = json.loads(metadata_path.read_text(encoding="utf-8"))
        probe = _probe(video_path)
    except Exception:
        return False
    return metadata.get("signature") == signature and probe["duration"] > 0


def _concat_manifest_line(path: Path) -> str:
    escaped = str(path.resolve()).replace("'", "'\\''")
    return f"file '{escaped}'"


def _compose_video(
    shots: list[dict],
    output_path: str | Path,
    cache_dir: str | Path,
    *,
    size: str,
    force_shot_ids: list[str] | None = None,
) -> dict:
    """按顺序合成多个镜头，只重做指纹变化或显式强制的镜头。"""
    width, height = _parse_size(size)
    normalized_size = f"{width}x{height}"
    if not isinstance(shots, list) or not shots:
        raise InvalidParameterError("shots", "shots 必须是至少包含一个镜头的列表")
    identifiers = [str(shot.get("id") or "").strip() for shot in shots]
    if any(not identifier for identifier in identifiers):
        raise InvalidParameterError("shots[].id", "每个镜头都必须有非空 id")
    if len(set(identifiers)) != len(identifiers):
        raise InvalidParameterError("shots[].id", "镜头 id 必须唯一，否则无法安全复用缓存")

    forced = set(force_shot_ids or [])
    unknown_forced = forced.difference(identifiers)
    if unknown_forced:
        raise InvalidParameterError("force_shot_ids", f"要重做的镜头不存在：{sorted(unknown_forced)}")

    ffmpeg = shutil.which("ffmpeg")
    if not ffmpeg:
        raise FFmpegNotFoundError("ffmpeg")
    output = Path(output_path).resolve()
    if output.suffix.lower() != ".mp4":
        raise InvalidParameterError("output_path", "完整视频输出必须使用 .mp4 扩展名")
    cache_root = Path(cache_dir).resolve()
    cache_root.mkdir(parents=True, exist_ok=True)
    output.parent.mkdir(parents=True, exist_ok=True)

    segment_paths: list[Path] = []
    shot_results: list[dict] = []
    for shot in shots:
        identifier = str(shot["id"]).strip()
        pre_rendered = str(shot.get("segment_path") or "").strip()
        if pre_rendered:
            segment = _validate_file(pre_rendered, f"shots[{identifier}].segment_path")
            probe = _probe(segment)
            segment_paths.append(segment)
            shot_results.append({
                "id": identifier,
                "cache_hit": False,
                "pre_rendered": True,
                "segment_path": str(segment),
                "duration": round(probe["duration"], 6),
            })
            continue
        if not str(shot.get("image_path") or "").strip():
            raise InvalidParameterError(
                "shots[].image_path",
                f"镜头 {identifier} 既没有 segment_path 也没有 image_path，无法渲染",
            )
        id_digest = hashlib.sha256(identifier.encode("utf-8")).hexdigest()[:12]
        safe_identifier = f"{_safe_id(identifier)}-{id_digest}"
        segment = cache_root / f"{safe_identifier}.mp4"
        metadata = cache_root / f"{safe_identifier}.json"
        signature = _signature(shot, normalized_size)
        cache_hit = identifier not in forced and _valid_cache(segment, metadata, signature)
        if not cache_hit:
            with tempfile.TemporaryDirectory(prefix=f"video-{safe_identifier}-", dir=cache_root) as temporary:
                temporary_segment = Path(temporary) / "segment.mp4"
                result = _render_shot(
                    shot.get("image_path"),
                    temporary_segment,
                    size=normalized_size,
                    duration=shot.get("duration"),
                    audio_path=shot.get("audio_path"),
                    audio_start=shot.get("audio_start"),
                    audio_end=shot.get("audio_end"),
                    subtitle=shot.get("subtitle"),
                    subtitle_language=shot.get("subtitle_language", "zh"),
                    motion=shot.get("motion"),
                )
                temporary_segment.replace(segment)
            temporary_metadata = metadata.with_suffix(".json.tmp")
            temporary_metadata.write_text(
                json.dumps(
                    {"signature": signature, "shot_id": identifier, "duration": result["duration"]},
                    ensure_ascii=False,
                    sort_keys=True,
                ),
                encoding="utf-8",
            )
            temporary_metadata.replace(metadata)
        cached_metadata = json.loads(metadata.read_text(encoding="utf-8"))
        segment_paths.append(segment)
        shot_results.append({
            "id": identifier,
            "cache_hit": cache_hit,
            "pre_rendered": False,
            "segment_path": str(segment),
            "duration": cached_metadata.get("duration"),
        })

    with tempfile.TemporaryDirectory(prefix="video-compose-", dir=output.parent) as temporary:
        temporary_dir = Path(temporary)
        manifest = temporary_dir / "segments.txt"
        manifest.write_text("\n".join(_concat_manifest_line(path) for path in segment_paths), encoding="utf-8")
        temporary_output = temporary_dir / "output.mp4"
        try:
            completed = subprocess.run(
                [
                    ffmpeg, "-y", "-f", "concat", "-safe", "0", "-i", str(manifest),
                    "-c", "copy", "-movflags", "+faststart", str(temporary_output),
                ],
                check=False,
                capture_output=True,
                text=True,
                encoding="utf-8",
                errors="replace",
                timeout=VIDEO_FFMPEG_TIMEOUT_SECONDS,
            )
        except subprocess.TimeoutExpired as exc:
            raise RenderTimeoutError("完整视频拼接", VIDEO_FFMPEG_TIMEOUT_SECONDS) from exc
        if completed.returncode != 0:
            detail = (completed.stderr or completed.stdout or "").strip()[-3000:]
            raise RenderError(f"完整视频拼接失败：{detail}")
        try:
            _probe(temporary_output)
            os.replace(temporary_output, output)
        except OSError as exc:
            raise CacheError(f"无法原子替换完整视频：{output}") from exc

    final_probe = _probe(output)
    return {
        "output_path": str(output),
        "duration": round(final_probe["duration"], 6),
        "shot_count": len(shot_results),
        "cache_hits": sum(1 for item in shot_results if item["cache_hit"]),
        "rendered_shots": sum(
            1 for item in shot_results if not item["cache_hit"] and not item.get("pre_rendered")
        ),
        "shots": shot_results,
    }
