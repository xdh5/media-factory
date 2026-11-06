"""逐段发布 YouTube 视频并持久化回执。"""

from __future__ import annotations

import json
from datetime import datetime, timezone
from pathlib import Path

from .._errors import AnimeError
from .media_artifacts import file_sha256, write_json, load_manifest
from .youtube_assets import require_host_thumbnail
from .youtube_metadata import part_title
from .youtube_platform import ensure_playlist_video, recover_youtube_upload, verify_processed_video


def publish_youtube(manifest_path: str, titles: list[str], descriptions: list[str], tags: list[str],
                    account_group: str, progress=None, receipt_saved=None,
                    playlist_title: str = "", require_completed: bool = True,
                    verify_processing: bool = True, *, upload_attempt_saved=None) -> dict:
    """逐段即时公开发布到指定动漫账号组，按文件摘要去重并逐条写回发布记录。"""
    from core.tools.media_records import list_publication_records, commit_publication_records, delete_publication_records
    from core.tools.publish_media.accounts import resolve_account_group
    from core.tools.publish_media.publisher import _publishing

    directory, parts = load_manifest(manifest_path, require_video_files=False)
    if json.loads((directory / "manifest.json").read_text(encoding="utf-8")).get("preview_only"):
        raise AnimeError("预览片段不能发布，请调用 anime_start_publication 由 Action 下载完整来源后发布")
    if len(titles) != 1 or len(descriptions) != 1:
        raise AnimeError("只需提供一个共用标题和描述")
    max_title_length = 80 if require_completed else 100
    if any(not title.strip() or len(title) > max_title_length for title in titles):
        raise AnimeError(f"YouTube 共用标题须为 1 到 {max_title_length} 个字符")
    if any(not text.strip() or len(text) > 5000 for text in descriptions):
        raise AnimeError("YouTube 描述须为 1 到 5000 个字符")
    tags = list(dict.fromkeys(str(tag).strip().lstrip("#") for tag in tags if str(tag).strip()))
    if sum(len(tag) + 3 for tag in tags) > 420:
        raise AnimeError("标签总长度须留出系统去重标记空间，请控制在 420 字符以内")
    if require_completed and "已完结" not in titles[0]:
        raise AnimeError("YouTube 标题关键词必须包含“已完结”")
    if require_completed and "#已完结" not in descriptions[0]:
        raise AnimeError("YouTube 描述底部 hashtag 必须包含 #已完结")
    if require_completed and "已完结" not in tags:
        raise AnimeError("YouTube 搜索标签必须包含“已完结”")
    for part in parts[:1]:
        if not (directory / f"youtube-intro-{part['part_index']}.json").is_file():
            raise AnimeError("请先完成第一段前一分钟转写，再根据原文生成共用发布文案")
    _publishing()
    from platform_api.account_registry import account_context, verify_account
    from platform_api.youtube import publish_to_youtube
    from platform_api.youtube.publish_to_youtube import _upload_tag

    from .accounts import production_config
    account_group = production_config(account_group)["account_group"]
    routes = resolve_account_group(account_group, "anime", ["youtube"])
    if len(routes) != 1:
        raise AnimeError("目标账号组必须明确对应一个 YouTube 频道")
    route = routes[0]
    verify_account(route)
    results = []
    for part in parts:
        index = part["part_index"]
        title = part_title(titles[0], index, int(part.get("part_count") or len(parts)))
        description = descriptions[0]
        path = Path(part["video_path"])
        if path.is_file():
            digest = file_sha256(path)
        else:
            digest = str(part.get("sha256") or "")
            if not digest:
                raise AnimeError(f"第 {index} 段本地成片和摘要都不存在，无法复用上传回执")
        run_id = f"anime-{digest}"
        previous = list_publication_records(business_line="anime", platform="youtube", run_id=run_id)
        matching = [row for row in previous if row["account_id"] == route["platform_account_id"]]
        live_record = None
        for row in matching:
            if not verify_processing:
                live_record = row
                break
            try:
                verify_processed_video(route, {"video_id": row["external_id"]}, part["duration_seconds"], progress, stale=True)
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
        receipt = directory / f"youtube-receipt-{index}.json"
        attempt_path = directory / f"youtube-upload-attempt-{index}.json"
        metadata = {"title": title, "description": description, "tags": tags,
                    "channel_id": route["platform_account_id"], "video_sha256": digest}
        if live_record:
            if receipt_saved:
                result = {"video_id": live_record["external_id"], "video_url": live_record["external_url"],
                          "reused": True}
                write_json(receipt, {**metadata, "title": live_record["title"], "result": result})
                receipt_saved(receipt)
            playlist = ensure_playlist_video(
                route, playlist_title, live_record["external_id"], index - 1, progress)
            results.append({"skipped": True, "record": live_record, "playlist": playlist})
            continue
        confirmed_invalid = bool(matching)
        write_json(directory / f"youtube-metadata-{index}.json", metadata)
        # 平台成功而数据库写回失败时，重试复用本地回执，不重复上传。回执视频已失效时作废并重传。
        saved = json.loads(receipt.read_text(encoding="utf-8")) if receipt.is_file() else {}
        publish_title = title
        result = None
        if saved.get("video_sha256") == digest and saved.get("channel_id") == route["platform_account_id"] and (saved.get("result") or {}).get("video_id"):
            result = saved["result"]
            publish_title = saved.get("title") or title
            if verify_processing:
                try:
                    verify_processed_video(route, result, part["duration_seconds"], progress, stale=True)
                except AnimeError as exc:
                    if not exc.details.get("reupload"):
                        raise
                    receipt.unlink(missing_ok=True)
                    confirmed_invalid = True
                    result = None
                    if progress:
                        progress("本地回执中的 YouTube 视频已失效，重新上传")
        if result is None:
            if not path.is_file():
                raise AnimeError(f"第 {index} 段没有本地成片且无可复用回执，无法上传")
            thumbnail = require_host_thumbnail(directory, index, title, digest)
            if progress:
                progress(
                    f"正在发布第 {index}/{int(part.get('part_count') or len(parts))} 段"
                    f"到 {account_group} YouTube")
            attempt = json.loads(attempt_path.read_text(encoding="utf-8")) if attempt_path.is_file() else {}
            if (not confirmed_invalid and attempt.get("video_sha256") == digest
                    and attempt.get("channel_id") == route["platform_account_id"]):
                result = recover_youtube_upload(route, attempt, thumbnail)
                publish_title = attempt["title"]
            else:
                write_json(attempt_path, {"channel_id": route["platform_account_id"], "video_sha256": digest,
                                           "title": title.strip()[:100], "upload_tag": _upload_tag(path, run_id)})
                if upload_attempt_saved:
                    upload_attempt_saved(attempt_path)
                with account_context(route) as account:
                    result = publish_to_youtube(route["platform_account_id"], path, title,
                        description=description, tags=tags, account=account, privacy_status="public",
                        publication_id=run_id, thumbnail_path=thumbnail,
                        on_progress=lambda percent, message: progress(f"YouTube：{message}（{percent:.1%}）") if progress else None)
                publish_title = title
            write_json(receipt, {**metadata, "title": publish_title, "result": result})
            if receipt_saved:
                receipt_saved(receipt)
            if verify_processing:
                verify_processed_video(route, result, part["duration_seconds"], progress)
        elif receipt_saved:
            receipt_saved(receipt)
        if not verify_processing:
            playlist = ensure_playlist_video(
                route, playlist_title, result["video_id"], index - 1, progress)
            results.append({
                "pending_processing": True,
                "result": result,
                "playlist": playlist,
                "part_index": index,
            })
            continue
        record = {"publication_id": run_id, "run_id": run_id, "business_line": "anime",
                  "platform": "youtube", "connector": "youtube", "account_id": route["platform_account_id"],
                  "content_part": index, "title": publish_title, "publish_mode": "immediate",
                  "publish_at": datetime.now(timezone.utc).isoformat(), "status": "published",
                  "external_id": result["video_id"], "external_url": result["video_url"]}
        stored = commit_publication_records([record])["records"][0]
        playlist = ensure_playlist_video(route, playlist_title, result["video_id"], index - 1, progress)
        results.append({"record": stored, "result": result, "playlist": playlist})
    playlists = [item["playlist"] for item in results if item.get("playlist")]
    return {"account_group": account_group, "published": results,
            "playlist": playlists[-1] if playlists else None}
