"""成片开头转写与动漫账号组 YouTube 发布，复用现有转写和官方发布接口。"""

from __future__ import annotations

import hashlib
import json
import os
import re
import subprocess
import time
from datetime import datetime, timezone
from pathlib import Path

from .._constants import OUTPUT_ROOT
from .._errors import AnimeError
from .compile import _executable, _subprocess_kwargs, _write_json


def _local_path(raw: str) -> Path:
    """Docker 读取同一工作区的 Windows 成片路径时映射到挂载目录。"""
    if os.name != "nt" and re.match(r"^[A-Za-z]:[\\/]", raw):
        normalized = raw.replace("\\", "/")
        marker = "/cache/output/anime/"
        if marker not in normalized:
            raise AnimeError("Windows 路径不属于动漫输出目录")
        return (OUTPUT_ROOT / normalized.split(marker, 1)[1]).resolve()
    return Path(raw).resolve()


def load_manifest(manifest_path: str) -> tuple[Path, list[dict]]:
    """仅接受动漫生产目录中的真实成片清单。"""
    path = _local_path(manifest_path)
    if not path.is_relative_to(OUTPUT_ROOT.resolve()) or path.name != "manifest.json":
        raise AnimeError("必须传动漫生产返回的 manifest.json")
    parts = json.loads(path.read_text(encoding="utf-8")).get("parts") or []
    if not parts:
        raise AnimeError("成片清单没有分段")
    for part in parts:
        video = _local_path(part["video_path"])
        if not video.is_relative_to(OUTPUT_ROOT.resolve()) or not video.is_file():
            raise AnimeError("成片文件不存在或不在动漫目录")
        part["video_path"] = str(video)
    return path.parent, parts


def transcribe_intros(manifest_path: str, progress=None) -> dict:
    """逐段抽取从零秒开始的前一分钟，缓存原始转写。"""
    from core.tools.transcribe import transcribe

    directory, parts = load_manifest(manifest_path)
    results = []
    for part in parts:
        index = part["part_index"]
        transcript = directory / f"youtube-intro-{index}.json"
        if not transcript.is_file():
            if progress:
                progress(f"正在转写第 {index} 段前一分钟")
            clip = directory / f"youtube-intro-{index}.mp3"
            subprocess.run([
                _executable("ffmpeg"), "-v", "error", "-y", "-i", part["video_path"],
                "-t", "60", "-vn", "-ac", "1", str(clip),
            ], check=True, capture_output=True, timeout=120, **_subprocess_kwargs())
            _write_json(transcript, transcribe(clip))
        results.append({"part_index": index, "original_title": part.get("title"),
                        "transcript": json.loads(transcript.read_text(encoding="utf-8"))})
    return {"manifest_path": manifest_path, "intros": results}


def _verify_processed_video(route: dict, result: dict, expected_duration: float, progress=None) -> None:
    """平台创建视频 ID 不代表上传完整，核验处理状态和实际时长后才登记成功。"""
    from googleapiclient.discovery import build
    from platform_api.account_registry import account_context
    from platform_api.youtube.publish_to_youtube import _load_credentials
    from platform_api.youtube._transport import authorized_http

    with account_context(route) as account:
        with build("youtube", "v3", http=authorized_http(_load_credentials(route["platform_account_id"], account)),
                   cache_discovery=False) as service:
            for _ in range(80):
                videos = service.videos().list(part="status,contentDetails,processingDetails,snippet", id=result["video_id"]).execute().get("items", [])
                if len(videos) != 1 or videos[0]["snippet"]["channelId"] != route["platform_account_id"]:
                    raise AnimeError("YouTube 未返回属于目标频道的视频")
                video = videos[0]
                status = video.get("status") or {}
                processing = (video.get("processingDetails") or {}).get("processingStatus")
                if status.get("uploadStatus") in {"failed", "rejected", "deleted"} or processing in {"failed", "terminated"}:
                    raise AnimeError("YouTube 视频上传或处理失败", {"video_id": result["video_id"], "status": status})
                if status.get("uploadStatus") == "processed" or processing == "succeeded":
                    duration = sum(float(number) * {"D": 86400, "H": 3600, "M": 60, "S": 1}[unit]
                                   for number, unit in re.findall(r"(\d+(?:\.\d+)?)([DHMS])", video["contentDetails"]["duration"]))
                    if abs(duration - expected_duration) > 3 or status.get("privacyStatus") != "public":
                        raise AnimeError("YouTube 视频时长或公开状态与预期不符，未登记发布成功")
                    return
                if progress:
                    progress("YouTube 正在处理视频，等待实际时长与公开状态核验")
                time.sleep(15)
    raise AnimeError("YouTube 视频仍在处理；回执已保留，稍后重试将继续核验，不重复上传")


def publish_youtube(manifest_path: str, titles: list[str], descriptions: list[str], tags: list[str],
                    account_group: str, progress=None) -> dict:
    """逐段即时公开发布到指定动漫账号组，按文件摘要去重并逐条写回发布记录。"""
    from core.tools.media_records import list_publication_records, commit_publication_records
    from core.tools.publish_media.accounts import resolve_account_group
    from core.tools.publish_media.publisher import _publishing

    directory, parts = load_manifest(manifest_path)
    if len(titles) != len(parts) or len(descriptions) != len(parts):
        raise AnimeError("每段视频必须对应一个标题和描述")
    if any(not title.strip() or len(title) > 100 for title in titles):
        raise AnimeError("YouTube 标题须为 1 到 100 个字符")
    if any(not text.strip() or len(text) > 5000 for text in descriptions):
        raise AnimeError("YouTube 描述须为 1 到 5000 个字符")
    tags = list(dict.fromkeys(str(tag).strip().lstrip("#") for tag in tags if str(tag).strip()))
    if sum(len(tag) + 3 for tag in tags) > 420:
        raise AnimeError("标签总长度须留出系统去重标记空间，请控制在 420 字符以内")
    for part in parts:
        if not (directory / f"youtube-intro-{part['part_index']}.json").is_file():
            raise AnimeError("请先完成各段前一分钟转写，再根据原文生成发布文案")
    _publishing()
    from platform_api.account_registry import account_context, verify_account
    from platform_api.youtube import publish_to_youtube

    if not account_group.strip():
        raise AnimeError("必须明确指定目标账号组")
    routes = resolve_account_group(account_group, "anime", ["youtube"])
    if len(routes) != 1:
        raise AnimeError("目标账号组必须明确对应一个 YouTube 频道")
    route = routes[0]
    verify_account(route)
    results = []
    for part, title, description in zip(parts, titles, descriptions):
        path = Path(part["video_path"])
        hasher = hashlib.sha256()
        with path.open("rb") as stream:
            for chunk in iter(lambda: stream.read(1024 * 1024), b""):
                hasher.update(chunk)
        digest = hasher.hexdigest()
        run_id = f"anime-{digest}"
        previous = list_publication_records(business_line="anime", platform="youtube", run_id=run_id)
        matching = [row for row in previous if row["account_id"] == route["platform_account_id"]]
        if matching:
            _verify_processed_video(route, {"video_id": matching[0]["external_id"]}, part["duration_seconds"], progress)
            results.append({"skipped": True, "record": matching[0]})
            continue
        index = part["part_index"]
        receipt = directory / f"youtube-receipt-{index}.json"
        metadata = {"title": title, "description": description, "tags": tags,
                    "channel_id": route["platform_account_id"], "video_sha256": digest}
        _write_json(directory / f"youtube-metadata-{index}.json", metadata)
        # 平台成功而数据库写回失败时，重试复用本地回执，不重复上传。
        saved = json.loads(receipt.read_text(encoding="utf-8")) if receipt.is_file() else {}
        if saved.get("video_sha256") == digest and saved.get("channel_id") == route["platform_account_id"]:
            result = saved["result"]
            title = saved["title"]
        else:
            if progress:
                progress(f"正在发布第 {index}/{len(parts)} 段到 {account_group} YouTube")
            with account_context(route) as account:
                result = publish_to_youtube(route["platform_account_id"], path, title,
                    description=description, tags=tags, account=account, privacy_status="public",
                    publication_id=run_id,
                    on_progress=lambda percent, message: progress(f"YouTube：{message}（{percent:.1%}）") if progress else None)
            _write_json(receipt, {**metadata, "result": result})
        _verify_processed_video(route, result, part["duration_seconds"], progress)
        record = {"publication_id": run_id, "run_id": run_id, "business_line": "anime",
                  "platform": "youtube", "connector": "youtube", "account_id": route["platform_account_id"],
                  "content_part": index, "title": title, "publish_mode": "immediate",
                  "publish_at": datetime.now(timezone.utc).isoformat(), "status": "published",
                  "external_id": result["video_id"], "external_url": result["video_url"]}
        stored = commit_publication_records([record])["records"][0]
        results.append({"record": stored, "result": result})
    return {"account_group": account_group, "published": results}
