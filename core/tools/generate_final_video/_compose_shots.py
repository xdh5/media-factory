"""按镜头渲或复用已有 MP4，再 copy 拼成一条视频。"""

from __future__ import annotations

import hashlib
import json
import os
import re
import shutil
import subprocess
import tempfile
from concurrent.futures import ThreadPoolExecutor, as_completed
from pathlib import Path

from core.tools.generate_shot import SHOT_RENDERER_VERSION, generate_shot_from_image

from ._constants import VIDEO_FFMPEG_TIMEOUT_SECONDS, VIDEO_FPS, VIDEO_SHOT_RENDER_WORKERS
from ._errors import (
    CacheError,
    FFmpegNotFoundError,
    InvalidParameterError,
    RenderError,
    RenderTimeoutError,
)
from ._ffmpeg import _probe, _validate_file
from ._output_name import _output_path
from ._size import parse_size

__all__ = ["compose_shots"]


def _concat_mp4s(segment_paths: list[Path], output_path: Path) -> dict:
    """按顺序 copy 拼接已编码的 MP4。"""
    if not segment_paths:
        raise InvalidParameterError("shots", "没有可拼接的镜头文件")
    paths = [_validate_file(path, f"segment[{index}]") for index, path in enumerate(segment_paths)]
    output = _output_path(output_path)
    ffmpeg = shutil.which("ffmpeg")
    if not ffmpeg:
        raise FFmpegNotFoundError("ffmpeg")
    with tempfile.TemporaryDirectory(prefix="video-concat-", dir=output.parent) as temporary:
        temporary_dir = Path(temporary)
        manifest = temporary_dir / "segments.txt"
        lines = []
        for path in paths:
            escaped = path.resolve().as_posix().replace("'", r"'\''")
            lines.append(f"file '{escaped}'")
        manifest.write_text("\n".join(lines), encoding="utf-8")
        temporary_output = temporary_dir / "output.mp4"
        try:
            completed = subprocess.run(
                [
                    ffmpeg, "-nostdin", "-hide_banner", "-y",
                    "-f", "concat", "-safe", "0", "-i", str(manifest),
                    "-c", "copy", str(temporary_output),
                ],
                check=False,
                capture_output=True,
                text=True,
                encoding="utf-8",
                errors="replace",
                timeout=VIDEO_FFMPEG_TIMEOUT_SECONDS,
            )
        except subprocess.TimeoutExpired as extra:
            raise RenderTimeoutError("视频拼接", VIDEO_FFMPEG_TIMEOUT_SECONDS) from extra
        if completed.returncode != 0:
            detail = (completed.stderr or completed.stdout or "").strip()[-3000:]
            raise RenderError(f"视频拼接失败：{detail}")
        try:
            _probe(temporary_output)
            os.replace(temporary_output, output)
        except OSError as extra:
            raise CacheError(f"无法原子替换视频：{output}") from extra
    probe = _probe(output)
    return {"output_path": str(output), "duration": round(probe["duration"], 6)}


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
    payload = {
        "renderer_version": SHOT_RENDERER_VERSION,
        "fps": VIDEO_FPS,
        "size": size,
        "shot": {
            "id": shot.get("id"),
            "duration": shot.get("duration"),
            "motion": shot.get("motion"),
        },
        "image": _hash_file(image),
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


def _render_missing_shot(item: dict, normalized_size: str, cache_root: Path) -> None:
    """把未命中缓存的镜头编进缓存文件；并行时每个镜头路径唯一。"""
    shot = item["shot"]
    identifier = item["identifier"]
    with tempfile.TemporaryDirectory(prefix=f"video-{item['safe_identifier']}-", dir=cache_root) as temporary:
        temporary_segment = Path(temporary) / "segment.mp4"
        result = generate_shot_from_image(
            shot.get("image_path"),
            temporary_segment,
            size=normalized_size,
            duration=shot.get("duration"),
            motion=shot.get("motion"),
        )
        temporary_segment.replace(item["segment"])
    temporary_metadata = item["metadata"].with_suffix(".json.tmp")
    temporary_metadata.write_text(
        json.dumps(
            {
                "signature": item["signature"],
                "shot_id": identifier,
                "duration": result["duration"],
            },
            ensure_ascii=False,
            sort_keys=True,
        ),
        encoding="utf-8",
    )
    temporary_metadata.replace(item["metadata"])


def compose_shots(
    shots: list[dict],
    output_path: str | Path,
    cache_dir: str | Path,
    *,
    size: str,
    force_shot_ids: list[str] | None = None,
    progress=None,
) -> dict:
    """按顺序合成多个镜头，只重做指纹变化或显式强制的镜头；未缓存镜头并行编码。"""
    width, height = parse_size(size)
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

    output = Path(output_path).resolve()
    if output.suffix.lower() != ".mp4":
        raise InvalidParameterError("output_path", "完整视频输出必须使用 .mp4 扩展名")
    cache_root = Path(cache_dir).resolve()
    cache_root.mkdir(parents=True, exist_ok=True)
    output.parent.mkdir(parents=True, exist_ok=True)

    planned: list[dict] = []
    for shot in shots:
        identifier = str(shot["id"]).strip()
        pre_rendered = str(shot.get("segment_path") or "").strip()
        if pre_rendered:
            planned.append({"kind": "pre_rendered", "identifier": identifier, "shot": shot})
            continue
        if not str(shot.get("image_path") or "").strip():
            raise InvalidParameterError(
                "shots[].image_path",
                f"镜头 {identifier} 既没有 segment_path 也没有 image_path，无法渲染",
            )
        try:
            duration = float(shot.get("duration") or 0)
        except (TypeError, ValueError) as extra:
            raise InvalidParameterError(
                "shots[].duration",
                f"镜头 {identifier} 的 duration 必须是正数",
            ) from extra
        if duration <= 0:
            raise InvalidParameterError(
                "shots[].duration",
                f"镜头 {identifier} 必须传入大于 0 的 duration",
            )
        id_digest = hashlib.sha256(identifier.encode("utf-8")).hexdigest()[:12]
        safe_identifier = f"{_safe_id(identifier)}-{id_digest}"
        segment = cache_root / f"{safe_identifier}.mp4"
        metadata = cache_root / f"{safe_identifier}.json"
        signature = _signature(shot, normalized_size)
        cache_hit = identifier not in forced and _valid_cache(segment, metadata, signature)
        planned.append({
            "kind": "render",
            "identifier": identifier,
            "shot": shot,
            "safe_identifier": safe_identifier,
            "segment": segment,
            "metadata": metadata,
            "signature": signature,
            "cache_hit": cache_hit,
        })

    missing = [item for item in planned if item["kind"] == "render" and not item["cache_hit"]]
    if missing:
        workers = max(1, min(VIDEO_SHOT_RENDER_WORKERS, len(missing)))
        with ThreadPoolExecutor(max_workers=workers) as executor:
            futures = [
                executor.submit(_render_missing_shot, item, normalized_size, cache_root)
                for item in missing
            ]
            for future in as_completed(futures):
                future.result()
                if progress:
                    done = sum(1 for item in missing if item["segment"].is_file())
                    progress(f"正在渲染镜头 {done}/{len(missing)}")

    segment_paths: list[Path] = []
    shot_results: list[dict] = []
    for item in planned:
        identifier = item["identifier"]
        if item["kind"] == "pre_rendered":
            segment = _validate_file(
                str(item["shot"].get("segment_path") or "").strip(),
                f"shots[{identifier}].segment_path",
            )
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
        cached_metadata = json.loads(item["metadata"].read_text(encoding="utf-8"))
        segment_paths.append(item["segment"])
        shot_results.append({
            "id": identifier,
            "cache_hit": item["cache_hit"],
            "pre_rendered": False,
            "segment_path": str(item["segment"]),
            "duration": cached_metadata.get("duration"),
        })

    composed = _concat_mp4s(segment_paths, output)
    return {
        "output_path": composed["output_path"],
        "duration": composed["duration"],
        "shot_count": len(shot_results),
        "cache_hits": sum(1 for item in shot_results if item["cache_hit"]),
        "rendered_shots": sum(
            1 for item in shot_results if not item["cache_hit"] and not item.get("pre_rendered")
        ),
        "shots": shot_results,
    }
