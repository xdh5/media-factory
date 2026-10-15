"""成片开头转写与动漫账号组 YouTube 发布，复用现有转写和官方发布接口。"""

from __future__ import annotations

import hashlib
import json
import os
import re
import subprocess
import time
from datetime import datetime, timezone
from io import BytesIO
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


_THUMBNAIL_SIZE = "1280x720"
_THUMBNAIL_MAX_BYTES = 2 * 1024 * 1024


def _thumbnail_prompt(title: str) -> str:
    """一次生成同时包含画面和标题，不接受先出图再叠字。"""
    return (
        "一次生成一张 16:9 YouTube 封面。画面和标题必须在同一次出图里一起完成，"
        "禁止先生成无字图片，再后期贴字、叠字或另外加文字图层。"
        "画风、线条、上色和角色造型语言与参考帧一致，不要改成写实照片或其他画风。"
        "把下面的标题原文作为画面的一部分完整、清晰地画出来，不要改字、漏字，也不要添加标题以外的文字：\n"
        f"{title}"
    )


def _extract_style_frame(video: Path, destination: Path, duration: float) -> None:
    """抽取成片中段附近的一帧，作为封面画风参考。"""
    offset = 8.0 if duration > 12 else max(0.2, duration / 2)
    completed = subprocess.run([
        _executable("ffmpeg"), "-v", "error", "-y", "-ss", f"{offset:.3f}", "-i", str(video),
        "-frames:v", "1", "-q:v", "2", str(destination),
    ], check=False, capture_output=True, timeout=120, **_subprocess_kwargs())
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


def _file_sha256(path: Path) -> str:
    hasher = hashlib.sha256()
    with path.open("rb") as stream:
        for chunk in iter(lambda: stream.read(1024 * 1024), b""):
            hasher.update(chunk)
    return hasher.hexdigest()


def prepare_youtube_thumbnails(manifest_path: str, titles: list[str]) -> dict:
    """只抽一帧画风参考，交给宿主一次生成带标题的封面。"""
    from core.tools.generate_image import ImageGenerationError, prepare_agent_image_tasks

    directory, parts = load_manifest(manifest_path)
    if len(titles) != len(parts):
        raise AnimeError("每段视频必须对应一个封面标题")
    if any(not str(title).strip() for title in titles):
        raise AnimeError("封面标题不能为空")
    prepared_tasks = []
    titles_by_image_id = {}
    digests = {}
    version = None
    frame = directory / "youtube-style-frame.jpg"
    sample = parts[0]
    _extract_style_frame(Path(sample["video_path"]), frame, float(sample["duration_seconds"]))
    for part, title in zip(parts, titles):
        index = part["part_index"]
        image_id = f"youtube-thumbnail-{index}"
        text = str(title).strip()
        titles_by_image_id[image_id] = text
        digests[image_id] = _file_sha256(Path(part["video_path"]))
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
                "标题必须和画面在同一次出图里一起生成，禁止先出无字图再叠字。"
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

    resolved = _local_path(context_path)
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
        _write_json(thumbnail.with_suffix(".json"), {"title": titles.get(image_id), "video_sha256": digests.get(image_id)})
        saved.append({"image_id": image_id, "thumbnail_path": thumbnail.resolve().as_posix()})
    return {"context_path": resolved.resolve().as_posix(), "thumbnails": saved}


def _require_host_thumbnail(directory: Path, index: int, title: str, digest: str) -> Path:
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


def _verify_processed_video(route: dict, result: dict, expected_duration: float, progress=None, *, stale: bool = False) -> None:
    """平台创建视频 ID 不代表上传完整，核验处理状态和实际时长后才登记成功。

    stale 为真时，连续多次查不到视频就要求重新上传。刚上传的视频允许继续等待索引。
    """
    from googleapiclient.discovery import build
    from platform_api.account_registry import account_context
    from platform_api.youtube.publish_to_youtube import _load_credentials
    from platform_api.youtube._transport import authorized_http

    missing = 0
    seen = False
    with account_context(route) as account:
        with build("youtube", "v3", http=authorized_http(_load_credentials(route["platform_account_id"], account)),
                   cache_discovery=False) as service:
            for _ in range(80):
                videos = service.videos().list(part="status,contentDetails,processingDetails,snippet", id=result["video_id"]).execute().get("items", [])
                if len(videos) != 1:
                    missing += 1
                    if missing >= 4 and (seen or stale):
                        raise AnimeError("YouTube 视频已不在目标频道，需重新上传", {"video_id": result.get("video_id"), "reupload": True})
                    if progress:
                        progress("YouTube 尚未返回目标频道视频，继续核验")
                    time.sleep(15)
                    continue
                video = videos[0]
                if (video.get("snippet") or {}).get("channelId") != route["platform_account_id"]:
                    raise AnimeError("YouTube 视频不属于目标频道，需重新上传", {"video_id": result.get("video_id"), "reupload": True})
                missing = 0
                seen = True
                status = video.get("status") or {}
                processing = (video.get("processingDetails") or {}).get("processingStatus")
                if status.get("uploadStatus") in {"failed", "rejected", "deleted"} or processing in {"failed", "terminated"}:
                    raise AnimeError("YouTube 视频上传或处理失败，需重新上传", {
                        "video_id": result["video_id"], "status": status, "reupload": True,
                    })
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
    from core.tools.media_records import list_publication_records, commit_publication_records, delete_publication_records
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
        live_record = None
        for row in matching:
            try:
                _verify_processed_video(route, {"video_id": row["external_id"]}, part["duration_seconds"], progress, stale=True)
            except AnimeError as exc:
                if not exc.details.get("reupload"):
                    raise
                record_id = row.get("id")
                if isinstance(record_id, int):
                    delete_publication_records([record_id])
                if progress:
                    progress("发布记录中的 YouTube 视频已失效，改为重新上传")
                continue
            live_record = row
            break
        if live_record:
            results.append({"skipped": True, "record": live_record})
            continue
        index = part["part_index"]
        receipt = directory / f"youtube-receipt-{index}.json"
        metadata = {"title": title, "description": description, "tags": tags,
                    "channel_id": route["platform_account_id"], "video_sha256": digest}
        _write_json(directory / f"youtube-metadata-{index}.json", metadata)
        # 平台成功而数据库写回失败时，重试复用本地回执，不重复上传。回执视频已失效时作废并重传。
        saved = json.loads(receipt.read_text(encoding="utf-8")) if receipt.is_file() else {}
        publish_title = title
        result = None
        if saved.get("video_sha256") == digest and saved.get("channel_id") == route["platform_account_id"] and (saved.get("result") or {}).get("video_id"):
            result = saved["result"]
            publish_title = saved.get("title") or title
            try:
                _verify_processed_video(route, result, part["duration_seconds"], progress, stale=True)
            except AnimeError as exc:
                if not exc.details.get("reupload"):
                    raise
                receipt.unlink(missing_ok=True)
                result = None
                if progress:
                    progress("本地回执中的 YouTube 视频已失效，重新上传")
        if result is None:
            thumbnail = _require_host_thumbnail(directory, index, title, digest)
            if progress:
                progress(f"正在发布第 {index}/{len(parts)} 段到 {account_group} YouTube")
            with account_context(route) as account:
                result = publish_to_youtube(route["platform_account_id"], path, title,
                    description=description, tags=tags, account=account, privacy_status="public",
                    publication_id=run_id, thumbnail_path=thumbnail,
                    on_progress=lambda percent, message: progress(f"YouTube：{message}（{percent:.1%}）") if progress else None)
            publish_title = title
            _write_json(receipt, {**metadata, "title": publish_title, "result": result})
            _verify_processed_video(route, result, part["duration_seconds"], progress)
        record = {"publication_id": run_id, "run_id": run_id, "business_line": "anime",
                  "platform": "youtube", "connector": "youtube", "account_id": route["platform_account_id"],
                  "content_part": index, "title": publish_title, "publish_mode": "immediate",
                  "publish_at": datetime.now(timezone.utc).isoformat(), "status": "published",
                  "external_id": result["video_id"], "external_url": result["video_url"]}
        stored = commit_publication_records([record])["records"][0]
        results.append({"record": stored, "result": result})
    return {"account_group": account_group, "published": results}
