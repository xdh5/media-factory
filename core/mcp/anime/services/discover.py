"""复用采集库获取主页作品，按需取证并复用已下载的来源。"""

from __future__ import annotations

import json
import shutil
import subprocess
import time
from pathlib import Path

import requests
from download_video import download
from list_author_works import list_author_works

from .._constants import OUTPUT_ROOT
from .._errors import AnimeError
from .compile import _executable, _probe, _subprocess_kwargs, _write_json, _write_text, assemble_videos


def load_discovery(discovery_path: str) -> tuple[Path, dict]:
    """只读取动漫输出目录内的主页发现记录。"""
    path = Path(discovery_path).resolve()
    if not path.is_relative_to(OUTPUT_ROOT.resolve()) or path.name != "discovery.json":
        raise AnimeError("discovery_path 必须是动漫任务返回的发现记录")
    if not path.is_file():
        raise AnimeError("主页发现记录不存在")
    return path.parent, json.loads(path.read_text(encoding="utf-8"))


def discover_series(profile_url: str, series_name: str, limit: int, directory: Path, progress) -> dict:
    """返回精简作品信息供宿主判断，不按关键词提前丢弃可能的别名作品。"""
    progress("正在调用 media-collector 获取作者作品")
    works = list_author_works(profile_url, limit)
    works = list({item["aweme_id"]: item for item in works if item.get("is_video")}.values())
    works.sort(key=lambda item: (item.get("published_at") or "", item["aweme_id"]))
    directory.mkdir(parents=True, exist_ok=True)
    payload = {"profile_url": profile_url, "series_name": series_name, "scan_limit": limit, "works": works}
    path = directory / "discovery.json"
    _write_json(path, payload)
    return {
        "discovery_path": str(path), "series_name": series_name,
        "scan_limit": limit, "scope": "仅保证已读取范围，不能据此宣称全主页或全剧完整",
        "works": [{key: item.get(key) for key in (
            "aweme_id", "title", "published_at", "duration_seconds",
        )} for item in works],
    }


def _source(directory: Path, work: dict) -> dict:
    """以作品 ID 缓存下载，取证与最终生产共用同一文件。"""
    folder = directory / "sources"
    folder.mkdir(exist_ok=True)
    path = folder / f"{work['aweme_id']}.mp4"
    metadata_path = path.with_suffix(".json")
    if path.is_file() and metadata_path.is_file():
        metadata = json.loads(metadata_path.read_text(encoding="utf-8"))
    else:
        metadata = download(work["work_url"], path)
        _write_json(metadata_path, metadata)
    probe = _probe(path)
    return {**metadata, "path": path, "probe": probe, "duration": probe["duration"],
            "share_text": work["work_url"]}


def inspect_works(discovery_path: str, work_ids: list[str], windows: list[float], cover_reason: str, progress) -> dict:
    """先返回片段口播证据，封面仅在宿主说明前序判断不足时识别。"""
    directory, discovery = load_discovery(discovery_path)
    works = {item["aweme_id"]: item for item in discovery["works"]}
    if not work_ids or len(work_ids) > 8 or len(set(work_ids)) != len(work_ids):
        raise AnimeError("每次取证需提供 1 到 8 个不重复作品 ID")
    if any(item not in works for item in work_ids):
        raise AnimeError("取证作品必须来自本次主页列表")
    if len(windows) > 4 or any(not 0 <= value <= 10800 for value in windows):
        raise AnimeError("每条最多取四个 45 秒片段，起点须在 0 到 10800 秒之间")
    if cover_reason.strip() and any(not list((directory / "sources").glob(
        f"{work_id}-speech-*.json")) for work_id in work_ids
    ):
        raise AnimeError("封面是最后兜底：请先完成对应作品的片段取证，再说明仍不明确的原因")
    results = []
    for work_id in work_ids:
        progress(f"正在取证作品 {work_id}")
        source = _source(directory, works[work_id])
        evidence = {"work_id": work_id, "duration_seconds": source["duration"], "windows": []}
        for start in windows:
            if start >= source["duration"]:
                raise AnimeError(f"作品 {work_id} 的片段起点超过视频长度")
            clip = directory / "sources" / f"{work_id}-speech-{start:g}.mp3"
            transcript = clip.with_suffix(".json")
            if not transcript.is_file():
                from core.tools.transcribe import transcribe

                subprocess.run([
                    _executable("ffmpeg"), "-v", "error", "-y", "-ss", str(start),
                    "-i", str(source["path"]), "-t", "45", "-vn", "-ac", "1", str(clip),
                ], check=True, capture_output=True, timeout=120, **_subprocess_kwargs())
                _write_json(transcript, transcribe(clip))
            text = json.loads(transcript.read_text(encoding="utf-8"))["text"]
            evidence["windows"].append({"start_seconds": start, "text": text})
        if cover_reason.strip():
            from core.tools.qwen_vision import analyze_image

            cover_result = directory / "sources" / f"{work_id}-cover.json"
            if not cover_result.is_file():
                url = works[work_id].get("cover_url") or source.get("cover_url")
                if not url:
                    raise AnimeError(f"作品 {work_id} 没有可读取的封面")
                response = requests.get(url, timeout=30)
                response.raise_for_status()
                if len(response.content) > 10 * 1024 * 1024:
                    raise AnimeError("封面超过 10MB")
                cover = directory / "sources" / f"{work_id}-cover.jpg"
                cover.write_bytes(response.content)
                result = analyze_image(cover, "只识别图片中实际可见的文字，禁止猜测。",
                                       "抄录剧名、集数、合集范围及其他可见文字。", max_tokens=500)
                _write_json(cover_result, {**result, "fallback_reason": cover_reason})
            evidence["cover"] = json.loads(cover_result.read_text(encoding="utf-8"))
        results.append(evidence)
    return {"discovery_path": discovery_path, "evidence": results}


def compile_selection(discovery_path: str, work_ids: list[str], selection_reason: str, progress) -> dict:
    """执行宿主确认的无重叠来源顺序，单个现成合集直接交付原文件。"""
    directory, discovery = load_discovery(discovery_path)
    works = {item["aweme_id"]: item for item in discovery["works"]}
    if not work_ids or len(set(work_ids)) != len(work_ids) or any(item not in works for item in work_ids):
        raise AnimeError("请选择本次主页中的不重复作品 ID")
    if not selection_reason.strip():
        raise AnimeError("必须记录作品匹配、集序、合集覆盖范围、去重和缺集情况")
    sources = []
    for index, work_id in enumerate(work_ids, 1):
        progress(f"正在下载选定来源 {index}/{len(work_ids)}")
        sources.append({**_source(directory, works[work_id]), "order": index})
    output = directory / f"selection-{time.time_ns()}"
    output.mkdir()
    _write_json(output / "selection.json", {"work_ids": work_ids, "reason": selection_reason,
                                            "series_name": discovery["series_name"]})
    if len(sources) != 1:
        result = assemble_videos(sources, output, progress=progress)
        result["selection_reason"] = selection_reason
        _write_json(output / "manifest.json", result)
        return result
    source = sources[0]
    path = output / "part-1.mp4"
    shutil.copy2(source["path"], path)
    part = {"part_index": 1, "part_count": 1, "video_path": str(path),
            "metadata_path": str(path.with_suffix(".json")),
            "duration_seconds": source["duration"], "title": source.get("title") or "",
            "description": source.get("description") or "", "topics": source.get("topics") or []}
    _write_json(path.with_suffix(".json"), part)
    _write_text(path.with_suffix(".txt"), f"标题：\n{part['title']}\n描述：\n{part['description']}\n话题：\n{' '.join(part['topics'])}")
    result = {"output_dir": str(output), "part_count": 1, "parts": [part],
              "original_file": True, "selection_reason": selection_reason}
    _write_json(output / "manifest.json", result)
    return result
