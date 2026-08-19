"""把本地竖版视频发到 Facebook Reels 和 Instagram Reels。"""

from __future__ import annotations

import os
import time
from pathlib import Path

import requests
from dotenv import load_dotenv

from ._constants import (
    FACEBOOK_GRAPH_BASE,
    INSTAGRAM_CONTAINER_POLL_SECONDS,
    INSTAGRAM_CONTAINER_TIMEOUT_SECONDS,
    INSTAGRAM_GRAPH_BASE,
    META_PLATFORMS,
    META_REQUEST_TIMEOUT_SECONDS,
    META_UPLOAD_TIMEOUT_SECONDS,
)
from ._errors import CredentialError, InvalidParameterError, MetaToolError, UploadError

load_dotenv()

__all__ = ["list_meta_accounts", "publish_facebook_reel", "publish_instagram_reel", "publish_meta_reels"]


def _env(name: str) -> str:
    return os.getenv(name, "").strip()


def _facebook_credentials() -> tuple[str, str]:
    page_id = _env("FACEBOOK_PAGE_ID")
    token = _env("FACEBOOK_PAGE_ACCESS_TOKEN")
    if not page_id or not token:
        raise CredentialError(
            "缺少 Facebook 主页凭据。请在 .env 填写 FACEBOOK_PAGE_ID 和 FACEBOOK_PAGE_ACCESS_TOKEN",
            {"required": ["FACEBOOK_PAGE_ID", "FACEBOOK_PAGE_ACCESS_TOKEN"]},
        )
    return page_id, token


def _instagram_credentials() -> tuple[str, str]:
    user_id = _env("INSTAGRAM_USER_ID")
    token = _env("INSTAGRAM_ACCESS_TOKEN")
    if not user_id or not token:
        raise CredentialError(
            "缺少 Instagram 凭据。请在 .env 填写 INSTAGRAM_USER_ID 和 INSTAGRAM_ACCESS_TOKEN",
            {"required": ["INSTAGRAM_USER_ID", "INSTAGRAM_ACCESS_TOKEN"]},
        )
    return user_id, token


def _raise_graph(response: requests.Response, action: str) -> dict:
    try:
        payload = response.json() if response.content else {}
    except ValueError:
        payload = {"raw": (response.text or "")[:1000]}
    if not response.ok or (isinstance(payload, dict) and payload.get("error")):
        error = (payload or {}).get("error") if isinstance(payload, dict) else {}
        message = str((error or {}).get("message") or response.text or f"HTTP {response.status_code}")
        if "pages_read_engagement" in message:
            message += (
                "。请到 Graph API Explorer 选这个 App，User/Page Token 勾选 pages_show_list、"
                "pages_read_engagement、pages_manage_posts、instagram_basic、instagram_content_publish，"
                "再换成 Page Token 写回 .env 的 FACEBOOK_PAGE_ACCESS_TOKEN"
            )
        raise UploadError(
            f"{action}失败：{message}",
            {"status": response.status_code, "type": (error or {}).get("type"), "code": (error or {}).get("code")},
        )
    if not isinstance(payload, dict):
        raise UploadError(f"{action}失败：接口没有返回对象")
    return payload


def _validate_video(video_path: str | Path) -> Path:
    video = Path(video_path).resolve()
    if not video.is_file():
        raise InvalidParameterError(f"视频文件不存在：{video}", {"parameter": "video_path"})
    if video.suffix.lower() != ".mp4":
        raise InvalidParameterError("Reels 视频必须是 .mp4", {"parameter": "video_path"})
    return video


def list_meta_accounts() -> list[dict]:
    """读取 .env 中已配置的 Facebook 主页和 Instagram 专业号，不回传 token。"""
    accounts = []
    page_id, page_token = _env("FACEBOOK_PAGE_ID"), _env("FACEBOOK_PAGE_ACCESS_TOKEN")
    accounts.append({"platform": "facebook", "account_id": page_id, "ready": bool(page_id and page_token)})
    ig_id, ig_token = _env("INSTAGRAM_USER_ID"), _env("INSTAGRAM_ACCESS_TOKEN")
    accounts.append({"platform": "instagram", "account_id": ig_id, "ready": bool(ig_id and ig_token)})
    return accounts


def publish_facebook_reel(
    video_path: str | Path | None = None,
    title: str = "",
    *,
    description: str = "",
    video_url: str = "",
) -> dict:
    """把本地视频或公开 URL 发到 Facebook Page Reels。"""
    page_id, token = _facebook_credentials()
    caption = str(description or title).strip()
    heading = str(title).strip()
    if not heading:
        raise InvalidParameterError("title 不能为空", {"parameter": "title"})
    hosted = str(video_url or "").strip()
    local = _validate_video(video_path) if video_path and not hosted else None
    if not hosted and local is None:
        raise InvalidParameterError("必须提供 video_path 或 video_url", {"parameter": "video_url"})
    start = requests.post(
        f"{FACEBOOK_GRAPH_BASE}/{page_id}/video_reels",
        data={"upload_phase": "start", "access_token": token},
        timeout=META_REQUEST_TIMEOUT_SECONDS,
    )
    session = _raise_graph(start, "Facebook Reels 创建上传会话")
    video_id = str(session.get("video_id") or "")
    upload_url = str(session.get("upload_url") or "")
    if not video_id or not upload_url:
        raise UploadError("Facebook 未返回 video_id 或 upload_url")
    if hosted:
        uploaded = requests.post(
            upload_url,
            headers={
                "Authorization": f"OAuth {token}",
                "file_url": hosted,
            },
            timeout=META_UPLOAD_TIMEOUT_SECONDS,
        )
    else:
        size = local.stat().st_size
        uploaded = requests.post(
            upload_url,
            headers={
                "Authorization": f"OAuth {token}",
                "offset": "0",
                "file_size": str(size),
                "Content-Type": "application/octet-stream",
            },
            data=local.read_bytes(),
            timeout=META_UPLOAD_TIMEOUT_SECONDS,
        )
    _raise_graph(uploaded, "Facebook Reels 上传文件")
    finish = requests.post(
        f"{FACEBOOK_GRAPH_BASE}/{page_id}/video_reels",
        data={
            "upload_phase": "finish",
            "video_id": video_id,
            "video_state": "PUBLISHED",
            "title": heading[:255],
            "description": caption[:10000],
            "access_token": token,
        },
        timeout=META_REQUEST_TIMEOUT_SECONDS,
    )
    _raise_graph(finish, "Facebook Reels 发布")
    permalink = f"https://www.facebook.com/reel/{video_id}"
    return {
        "platform": "facebook",
        "success": True,
        "media_id": video_id,
        "permalink": permalink,
        "page_id": page_id,
        "video_url": hosted or None,
    }


def _wait_container(base: str, container_id: str, token: str) -> None:
    deadline = time.monotonic() + INSTAGRAM_CONTAINER_TIMEOUT_SECONDS
    last = ""
    while time.monotonic() < deadline:
        status = requests.get(
            f"{base}/{container_id}",
            params={"fields": "status_code,status", "access_token": token},
            timeout=META_REQUEST_TIMEOUT_SECONDS,
        )
        payload = _raise_graph(status, "Instagram Reels 查询处理状态")
        code = str(payload.get("status_code") or "").upper()
        last = str(payload.get("status") or code)
        if code == "FINISHED":
            return
        if code in {"ERROR", "EXPIRED"}:
            raise UploadError(f"Instagram 处理 Reels 失败：{last or code}", {"status_code": code})
        time.sleep(INSTAGRAM_CONTAINER_POLL_SECONDS)
    raise UploadError(
        f"Instagram Reels 处理超时（{INSTAGRAM_CONTAINER_TIMEOUT_SECONDS} 秒），最后状态：{last or '未知'}",
        {"container_id": container_id, "fix": "请确认视频为 H.264 竖版 mp4 后重试"},
    )


def _publish_instagram_resumable(base: str, user_id: str, token: str, video: Path, caption: str) -> dict:
    init = requests.post(
        f"{base}/{user_id}/media",
        data={
            "media_type": "REELS",
            "upload_type": "resumable",
            "share_to_feed": "true",
            "caption": caption[:2200],
            "access_token": token,
        },
        timeout=META_REQUEST_TIMEOUT_SECONDS,
    )
    container = _raise_graph(init, "Instagram Reels 创建容器")
    container_id = str(container.get("id") or "")
    upload_uri = str(container.get("uri") or "")
    if not container_id or not upload_uri:
        raise UploadError("Instagram 未返回容器 id 或上传地址")
    size = video.stat().st_size
    uploaded = requests.post(
        upload_uri,
        headers={
            "Authorization": f"OAuth {token}",
            "offset": "0",
            "file_size": str(size),
            "Content-Type": "application/octet-stream",
        },
        data=video.read_bytes(),
        timeout=META_UPLOAD_TIMEOUT_SECONDS,
    )
    if uploaded.status_code >= 400:
        _raise_graph(uploaded, "Instagram Reels 上传文件")
    _wait_container(base, container_id, token)
    published = requests.post(
        f"{base}/{user_id}/media_publish",
        data={"creation_id": container_id, "access_token": token},
        timeout=META_REQUEST_TIMEOUT_SECONDS,
    )
    media = _raise_graph(published, "Instagram Reels 发布")
    media_id = str(media.get("id") or "")
    if not media_id:
        raise UploadError("Instagram 未返回媒体 id")
    permalink = ""
    details = requests.get(
        f"{base}/{media_id}",
        params={"fields": "permalink,id", "access_token": token},
        timeout=META_REQUEST_TIMEOUT_SECONDS,
    )
    if details.ok:
        permalink = str(_raise_graph(details, "Instagram 读取链接").get("permalink") or "")
    return {
        "platform": "instagram",
        "success": True,
        "media_id": media_id,
        "permalink": permalink or f"https://www.instagram.com/reel/{media_id}",
        "user_id": user_id,
    }


def _publish_instagram_from_url(base: str, user_id: str, token: str, video_url: str, caption: str) -> dict:
    init = requests.post(
        f"{base}/{user_id}/media",
        data={
            "media_type": "REELS",
            "video_url": video_url,
            "share_to_feed": "true",
            "caption": caption[:2200],
            "access_token": token,
        },
        timeout=META_REQUEST_TIMEOUT_SECONDS,
    )
    container = _raise_graph(init, "Instagram Reels 创建容器")
    container_id = str(container.get("id") or "")
    if not container_id:
        raise UploadError("Instagram 未返回容器 id")
    _wait_container(base, container_id, token)
    published = requests.post(
        f"{base}/{user_id}/media_publish",
        data={"creation_id": container_id, "access_token": token},
        timeout=META_REQUEST_TIMEOUT_SECONDS,
    )
    media = _raise_graph(published, "Instagram Reels 发布")
    media_id = str(media.get("id") or "")
    if not media_id:
        raise UploadError("Instagram 未返回媒体 id")
    permalink = ""
    details = requests.get(
        f"{base}/{media_id}",
        params={"fields": "permalink,id", "access_token": token},
        timeout=META_REQUEST_TIMEOUT_SECONDS,
    )
    if details.ok:
        permalink = str(_raise_graph(details, "Instagram 读取链接").get("permalink") or "")
    return {
        "platform": "instagram",
        "success": True,
        "media_id": media_id,
        "permalink": permalink or f"https://www.instagram.com/reel/{media_id}",
        "user_id": user_id,
        "video_url": video_url,
    }


def publish_instagram_reel(
    video_path: str | Path | None = None,
    caption: str = "",
    *,
    video_url: str = "",
) -> dict:
    """优先用公开 video_url（R2）；没有 URL 时再尝试断点续传。"""
    text = str(caption).strip()
    if not text:
        raise InvalidParameterError("caption 不能为空", {"parameter": "caption"})
    hosted = str(video_url or "").strip()
    user_id, ig_token = _instagram_credentials()
    if hosted:
        try:
            return _publish_instagram_from_url(INSTAGRAM_GRAPH_BASE, user_id, ig_token, hosted, text)
        except UploadError:
            _page_id, page_token = _facebook_credentials()
            return _publish_instagram_from_url(FACEBOOK_GRAPH_BASE, user_id, page_token, hosted, text)
    video = _validate_video(video_path) if video_path else None
    if video is None:
        raise InvalidParameterError("必须提供 video_path 或 video_url", {"parameter": "video_url"})
    errors: list[str] = []
    try:
        _page_id, page_token = _facebook_credentials()
        return _publish_instagram_resumable(FACEBOOK_GRAPH_BASE, user_id, page_token, video, text)
    except (CredentialError, UploadError) as error:
        errors.append(error.message)
    try:
        return _publish_instagram_resumable(INSTAGRAM_GRAPH_BASE, user_id, ig_token, video, text)
    except UploadError as error:
        errors.append(error.message)
        raise UploadError(
            "Instagram Reels 上传失败。请先把视频传到 Cloudflare R2 再传 video_url，"
            "或给 Page Token 勾选 pages_read_engagement、instagram_content_publish。"
            f"详情：{'；'.join(errors)}",
            {"fix": "R2_PUBLIC_BASE_URL 或 pages_read_engagement"},
        ) from error


def publish_meta_reels(
    video_path: str | Path | None = None,
    title: str = "",
    *,
    description: str = "",
    platforms: list[str] | None = None,
    video_url: str = "",
) -> dict:
    """按平台列表发布同一条视频；有公开 URL 时 Facebook/Instagram 都走该地址。"""
    selected = [str(item).strip().lower() for item in (platforms or list(META_PLATFORMS))]
    unknown = [item for item in selected if item not in META_PLATFORMS]
    if unknown:
        raise InvalidParameterError(
            f"不支持的 Meta 平台：{unknown}。可选 {list(META_PLATFORMS)}",
            {"parameter": "platforms"},
        )
    heading = str(title).strip()
    if not heading:
        raise InvalidParameterError("title 不能为空", {"parameter": "title"})
    caption = str(description or heading).strip()
    hosted = str(video_url or "").strip()
    results = []
    for platform in selected:
        try:
            if platform == "facebook":
                results.append(publish_facebook_reel(video_path, heading, description=caption, video_url=hosted))
            else:
                results.append(publish_instagram_reel(video_path, caption, video_url=hosted))
        except MetaToolError as error:
            results.append({
                "platform": platform,
                "success": False,
                "error": error.to_dict()["error"],
            })
    return {"title": heading, "video_url": hosted or None, "platforms": results}
