"""撤销官方平台预约，确认成功后清理对应数据库回执。"""

import time
from datetime import datetime
from zoneinfo import ZoneInfo

import requests

from tools.database.publication_records import delete_publication_records, list_publication_records
from .accounts import list_account_groups
from .content import normalize_platforms, normalize_publish_date
from ._errors import InvalidPublishRequestError, MediaPublisherCommandError


def _cancel_youtube(record: dict, member: dict, publish_date: str) -> None:
    from googleapiclient.discovery import build
    from google_auth_httplib2 import AuthorizedHttp
    from platform_api.account_registry import account_context
    from platform_api.youtube.publish_to_youtube import _load_credentials, YouTubeHttp

    with account_context(member) as account:
        transport = YouTubeHttp()
        try:
            credentials = _load_credentials(member["connector_account_id"], account)
            youtube = build("youtube", "v3", http=AuthorizedHttp(credentials, http=transport), cache_discovery=False)
            channels = youtube.channels().list(part="id", mine=True).execute()["items"]
            if {row["id"] for row in channels} != {member["platform_account_id"]}:
                raise InvalidPublishRequestError("YouTube 实际授权频道与预约账号不一致")
            videos = youtube.videos().list(part="snippet,status", id=record["external_id"]).execute()["items"]
            if not videos:
                return
            video = videos[0]
            if video["snippet"]["channelId"] != member["platform_account_id"]:
                raise InvalidPublishRequestError("YouTube 预约视频不属于目标频道")
            status = video["status"]
            if status["privacyStatus"] != "private":
                raise InvalidPublishRequestError("视频已经公开或转为不公开，不能按预约撤销")
            if not status.get("publishAt"):
                return
            actual_date = datetime.fromisoformat(status["publishAt"].replace("Z", "+00:00")).astimezone(ZoneInfo("Asia/Shanghai")).date().isoformat()
            if actual_date != publish_date:
                raise InvalidPublishRequestError("YouTube 实际预约日期已变化，保留回执供核对")
            updated = {key: status[key] for key in (
                "license", "embeddable", "publicStatsViewable", "selfDeclaredMadeForKids", "containsSyntheticMedia",
            ) if key in status}
            updated.update({"privacyStatus": "private", "publishAt": None})
            youtube.videos().update(part="status", body={"id": video["id"], "status": updated}).execute()
            # YouTube 的状态回读有短暂延迟，只轮询确认，不重复发送更新请求。
            deadline = time.monotonic() + 30
            while True:
                latest = youtube.videos().list(part="status", id=video["id"]).execute()["items"]
                if not latest or (latest[0]["status"]["privacyStatus"] == "private"
                                  and not latest[0]["status"].get("publishAt")):
                    return
                if time.monotonic() >= deadline:
                    raise MediaPublisherCommandError("YouTube 尚未确认取消预约，保留数据库回执")
                time.sleep(1)
        finally:
            transport.close()


def _cancel_zernio(record: dict, member: dict, allowed_accounts: set[str], publish_date: str) -> None:
    from platform_api.account_registry import account_context, env_value

    url = f"https://zernio.com/api/v1/posts/{record['external_id']}"
    with account_context(member):
        headers = {"Authorization": f"Bearer {env_value('ZERNIO_API_KEY')}"}
        response = requests.get(url, headers=headers, timeout=30)
        if response.status_code == 404:
            return
        response.raise_for_status()
        payload = response.json()
        post = payload.get("post") or payload.get("data") or payload
        accounts = {item["accountId"]["_id"] if isinstance(item["accountId"], dict) else item["accountId"]
                    for item in post["platforms"]}
        if member["connector_account_id"] not in accounts or not accounts <= allowed_accounts:
            raise InvalidPublishRequestError("Zernio 帖子包含本次取消范围以外的账号")
        if post["status"] not in {"scheduled", "cancelled", "canceled"}:
            raise InvalidPublishRequestError(f"Zernio 帖子不是待取消预约：{post['status']}")
        if post["status"] == "scheduled":
            actual_date = datetime.fromisoformat(post["scheduledFor"].replace("Z", "+00:00")).astimezone(ZoneInfo("Asia/Shanghai")).date().isoformat()
            if actual_date != publish_date:
                raise InvalidPublishRequestError("Zernio 实际预约日期已变化，保留回执供核对")
        response = requests.delete(url, headers=headers, timeout=30)
        response.raise_for_status()
        checked = requests.get(url, headers=headers, timeout=30)
        if checked.status_code != 404:
            raise MediaPublisherCommandError("Zernio 尚未确认删除预约，保留数据库回执")


def cancel_scheduled_publications(
    business_line: str, publish_date: str, account_group: str, platforms: list[str], progress=None,
) -> dict:
    """按现有预约回执逐条撤销；平台确认后才删除该条回执，失败项保留。"""
    publish_date = normalize_publish_date(publish_date)
    platforms = normalize_platforms(platforms)
    groups = list_account_groups(business_line, account_group, platforms)["groups"]
    members = {(member["platform"], member["platform_account_id"]): member
               for group in groups for member in group["members"]}
    if not members:
        raise InvalidPublishRequestError("没有匹配的发布账号组")
    if any(member["connector"] not in {"youtube", "zernio"} for member in members.values()):
        raise InvalidPublishRequestError("预约取消目前只支持 YouTube 与 Zernio 官方接口")
    records = [record for record in list_publication_records(business_line=business_line, publish_date=publish_date)
               if record["status"] == "scheduled" and (record["platform"], record["account_id"]) in members]
    cancelled, failed = [], []
    allowed_accounts = {member["connector_account_id"] for member in members.values()}
    for record in records:
        try:
            if not record.get("external_id"):
                raise InvalidPublishRequestError("回执缺少平台预约 ID，无法确认取消，保留回执")
            if progress:
                progress(f"正在撤销 {record['platform']}：{record['title']}")
            member = members[(record["platform"], record["account_id"])]
            if member["connector"] == "youtube":
                _cancel_youtube(record, member, publish_date)
            else:
                _cancel_zernio(record, member, allowed_accounts, publish_date)
            deleted = delete_publication_records([record["id"]])
            if record["id"] not in deleted["deleted_ids"]:
                raise MediaPublisherCommandError("平台已取消，但数据库未确认回执清理")
            cancelled.append({"record_id": record["id"], "platform": record["platform"],
                              "external_id": record["external_id"], "receipt_deleted": True})
        except Exception as exc:
            failed.append({"record_id": record["id"], "platform": record["platform"], "error": str(exc)})
    result = {"cancelled": cancelled, "failed": failed, "matched_count": len(records)}
    if not records:
        result["notice"] = "未找到数据库预约回执，不能据此判断平台没有孤立预约"
    if failed:
        raise MediaPublisherCommandError("部分预约取消或回执清理失败", result)
    return result
