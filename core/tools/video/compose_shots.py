"""使用逐镜头内容指纹缓存合成完整视频。"""

from __future__ import annotations

import hashlib
import json
import re
import tempfile
from concurrent.futures import ThreadPoolExecutor, as_completed
from pathlib import Path

from ._constants import VIDEO_FPS, VIDEO_RENDERER_VERSION, VIDEO_SHOT_RENDER_WORKERS
from ._errors import InvalidParameterError
from ._select_subtitle import _parse_size
from .concat_videos import concat_videos
from .render_shot import _probe, _validate_file, render_shot

__all__ = ["compose_shots"]


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


def _render_missing_shot(item: dict, normalized_size: str, cache_root: Path) -> None:
    """把未命中缓存的镜头编进缓存文件；并行时每个镜头路径唯一。"""
    shot = item["shot"]
    identifier = item["identifier"]
    with tempfile.TemporaryDirectory(prefix=f"video-{item['safe_identifier']}-", dir=cache_root) as temporary:
        temporary_segment = Path(temporary) / "segment.mp4"
        result = render_shot(
            shot.get("image_path"),
            temporary_segment,
            size=normalized_size,
            duration=shot.get("duration"),
            audio_path=shot.get("audio_path"),
            audio_start=shot.get("audio_start"),
            audio_end=shot.get("audio_end"),
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
) -> dict:
    """按顺序合成多个镜头，只重做指纹变化或显式强制的镜头；未缓存镜头并行编码。"""
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

    composed = concat_videos(segment_paths, output)
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
