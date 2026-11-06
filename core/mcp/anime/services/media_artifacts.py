"""读写动漫成片清单和缓存产物。"""

from __future__ import annotations

import hashlib
import json
import os
import re
from pathlib import Path

from .._constants import OUTPUT_ROOT
from .._errors import AnimeError

def resolve_output_path(raw: str) -> Path:
    """Docker 读取同一工作区的 Windows 成片路径时映射到挂载目录。"""
    if os.name != "nt" and re.match(r"^[A-Za-z]:[\\/]", raw):
        normalized = raw.replace("\\", "/")
        marker = "/cache/output/anime/"
        if marker not in normalized:
            raise AnimeError("Windows 路径不属于动漫输出目录")
        return (OUTPUT_ROOT / normalized.split(marker, 1)[1]).resolve()
    return Path(raw).resolve()


def load_manifest(manifest_path: str, *, require_video_files: bool = True) -> tuple[Path, list[dict]]:
    """仅接受动漫生产目录中的真实成片清单。"""
    path = resolve_output_path(manifest_path)
    if not path.is_relative_to(OUTPUT_ROOT.resolve()) or path.name != "manifest.json":
        raise AnimeError("必须传动漫生产返回的 manifest.json")
    parts = json.loads(path.read_text(encoding="utf-8")).get("parts") or []
    if not parts:
        raise AnimeError("成片清单没有分段")
    for part in parts:
        video = resolve_output_path(part["video_path"])
        if not video.is_relative_to(OUTPUT_ROOT.resolve()) or (require_video_files and not video.is_file()):
            raise AnimeError("成片文件不存在或不在动漫目录")
        part["video_path"] = str(video)
    return path.parent, parts


def file_sha256(path: Path) -> str:
    hasher = hashlib.sha256()
    with path.open("rb") as stream:
        for chunk in iter(lambda: stream.read(1024 * 1024), b""):
            hasher.update(chunk)
    return hasher.hexdigest()


def write_json(path: Path, payload: dict) -> None:
    path.write_text(json.dumps(payload, ensure_ascii=False, indent=2), encoding="utf-8")


def write_text(path: Path, text: str) -> None:
    path.write_text(text, encoding="utf-8")
