"""核验 YouTube 视频、恢复上传结果并维护播放列表。"""

from __future__ import annotations

import json
import re
import time
from pathlib import Path

from .._errors import AnimeError




def verify_processed_video(route: dict, result: dict, expected_duration: float, progress=None, *, stale: bool = False) -> None:
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


def ensure_playlist_video(route: dict, playlist_title: str, video_id: str,
                           position: int, progress=None) -> dict | None:
    """创建或复用频道播放列表，并幂等加入视频。普通频道凭 force-ssl 授权即可使用。"""
    title = str(playlist_title or "").strip()[:150]
    if not title:
        return None
    from googleapiclient.discovery import build
    from googleapiclient.errors import HttpError
    from platform_api.account_registry import account_context
    from platform_api.youtube.publish_to_youtube import _load_credentials
    from platform_api.youtube._transport import authorized_http

    with account_context(route) as account:
        with build("youtube", "v3", http=authorized_http(_load_credentials(route["platform_account_id"], account)),
                   cache_discovery=False) as service:
            playlist_id = ""
            page_token = None
            while True:
                response = service.playlists().list(
                    part="snippet,status", mine=True, maxResults=50, pageToken=page_token).execute()
                matched = next((
                    item for item in response.get("items") or []
                    if str((item.get("snippet") or {}).get("title") or "").strip() == title
                ), None)
                if matched:
                    playlist_id = str(matched["id"])
                    break
                page_token = response.get("nextPageToken")
                if not page_token:
                    break
            if not playlist_id:
                created = service.playlists().insert(
                    part="snippet,status",
                    body={"snippet": {"title": title}, "status": {"privacyStatus": "public"}},
                ).execute()
                playlist_id = str(created["id"])
                if progress:
                    progress(f"已创建 YouTube 播放列表：{title}")
            # 按视频 ID 精确查重，避免遍历列表时使用平台返回的失效分页令牌。
            for attempt in range(7):
                try:
                    response = service.playlistItems().list(
                        part="snippet,contentDetails", playlistId=playlist_id,
                        videoId=video_id, maxResults=50).execute()
                    break
                except HttpError as exc:
                    errors = json.loads(exc.content).get("error", {}).get("errors", [])
                    if (exc.resp.status != 404
                            or not any(item.get("reason") == "playlistNotFound" for item in errors)
                            or attempt == 6):
                        raise
                    if progress:
                        progress(f"YouTube 播放列表查询返回 404，5 秒后重试（{attempt + 1}/6）")
                    time.sleep(5)
            for item in response.get("items") or []:
                if str((item.get("contentDetails") or {}).get("videoId") or "") != video_id:
                    continue
                snippet = item.get("snippet") or {}
                if int(snippet.get("position") or 0) != position:
                    service.playlistItems().update(
                        part="snippet",
                        body={"id": item["id"], "snippet": {
                            "playlistId": playlist_id,
                            "position": position,
                            "resourceId": {"kind": "youtube#video", "videoId": video_id},
                        }},
                    ).execute()
                return {"playlist_id": playlist_id,
                        "playlist_url": f"https://www.youtube.com/playlist?list={playlist_id}"}
            service.playlistItems().insert(
                part="snippet",
                body={"snippet": {
                    "playlistId": playlist_id,
                    "position": position,
                    "resourceId": {"kind": "youtube#video", "videoId": video_id},
                }},
            ).execute()
            if progress:
                progress(f"已加入 YouTube 播放列表：{title}")
            return {"playlist_id": playlist_id,
                    "playlist_url": f"https://www.youtube.com/playlist?list={playlist_id}"}


def recover_youtube_upload(route: dict, attempt: dict, thumbnail: Path) -> dict:
    from googleapiclient.discovery import build
    from platform_api.youtube._transport import authorized_http
    from platform_api.youtube.publish_to_youtube import _apply_thumbnail, _find_existing_video, _load_credentials
    from platform_api.account_registry import account_context

    channel_id = route["platform_account_id"]
    with account_context(route) as account:
        with build("youtube", "v3", http=authorized_http(_load_credentials(channel_id, account)),
                   cache_discovery=False) as youtube:
            existing = _find_existing_video(youtube, channel_id, attempt["title"], attempt["upload_tag"])
            if not existing:
                raise AnimeError("YouTube 上传结果待核对，频道暂未查到匹配的视频。请核查频道上传记录后再处理。",
                                 {"channel_id": channel_id, "upload_tag": attempt["upload_tag"]})
            video_id = existing["video_id"]
            _apply_thumbnail(youtube, video_id, thumbnail)
    return {"video_id": video_id, "video_url": f"https://www.youtube.com/watch?v={video_id}",
            "channel_id": channel_id, "privacy_status": "public", "publish_at": None,
            "scheduled": False, "reused": True}
