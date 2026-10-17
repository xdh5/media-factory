"""财经口播稿库：转写入库、去重、占用，以及作者名单和整篇广告记录。"""

from __future__ import annotations

from core.tools.media_records import MediaRecordsRequestError
from core.tools.media_records.client import _request


def list_source_authors() -> list[dict]:
    """按添加顺序返回财经作者名单。"""
    payload = _request("GET", "/v1/finance-source-authors")
    if not isinstance(payload, dict) or not isinstance(payload.get("authors"), list):
        raise MediaRecordsRequestError("财经作者名单接口缺少 authors 数组")
    authors = []
    for item in payload["authors"]:
        if not isinstance(item, dict):
            raise MediaRecordsRequestError("财经作者名单包含无效记录")
        sec_user_id = str(item.get("sec_user_id") or "").strip()
        profile_url = str(item.get("profile_url") or "").strip()
        if not sec_user_id or not profile_url:
            raise MediaRecordsRequestError("财经作者名单缺少主页标识")
        authors.append({
            "sec_user_id": sec_user_id,
            "profile_url": profile_url,
            "display_name": str(item.get("display_name") or "").strip(),
            "created_at": str(item.get("created_at") or ""),
            "updated_at": str(item.get("updated_at") or ""),
        })
    return authors


def add_source_author(*, sec_user_id: str, profile_url: str, display_name: str = "") -> dict:
    """把一位作者写入财经作者名单。已存在时更新显示名。"""
    payload = _request(
        "POST",
        "/v1/finance-source-authors",
        body={
            "sec_user_id": sec_user_id,
            "profile_url": profile_url,
            "display_name": display_name,
        },
    )
    author = payload.get("author") if isinstance(payload, dict) else None
    if not isinstance(author, dict) or not str(author.get("sec_user_id") or "").strip():
        raise MediaRecordsRequestError("财经作者写入接口缺少 author")
    return author


def remove_source_author(sec_user_id: str) -> dict:
    """从财经作者名单删除一位作者。"""
    payload = _request(
        "DELETE",
        "/v1/finance-source-authors",
        body={"sec_user_id": sec_user_id},
    )
    author = payload.get("author") if isinstance(payload, dict) else None
    if not isinstance(author, dict) or not str(author.get("sec_user_id") or "").strip():
        raise MediaRecordsRequestError("财经作者删除接口缺少 author")
    return author


def list_saved_script_ids() -> list[str]:
    """返回已经入库的口播稿作品 ID，抓取时用来去重。"""
    payload = _request("GET", "/v1/douyin-research/ids")
    if not isinstance(payload, dict) or not isinstance(payload.get("aweme_ids"), list):
        raise MediaRecordsRequestError("已入库口播稿接口缺少 aweme_ids 数组")
    return [str(value) for value in payload["aweme_ids"] if str(value).strip()]


def save_transcribed_scripts(records: list[dict]) -> dict:
    """把转写完成的口播稿写入财经稿件库。"""
    payload = _request(
        "POST",
        "/v1/douyin-research/commit",
        body={"records": records},
    )
    if not isinstance(payload, dict) or not isinstance(payload.get("records"), list):
        raise MediaRecordsRequestError("转写稿写入接口缺少 records 数组")
    return payload


def list_rejected_ad_video_ids() -> list[str]:
    """返回已判定为整篇广告的作品 ID，避免下次重复下载。"""
    payload = _request("GET", "/v1/finance-rejected-awemes")
    if not isinstance(payload, dict) or not isinstance(payload.get("aweme_ids"), list):
        raise MediaRecordsRequestError("整篇广告记录接口缺少 aweme_ids 数组")
    return [str(value) for value in payload["aweme_ids"] if str(value).strip()]


def remember_rejected_ad_video(aweme_id: str) -> dict:
    """记下整篇广告作品，下次抓取直接跳过。"""
    payload = _request(
        "POST",
        "/v1/finance-rejected-awemes",
        body={"aweme_id": aweme_id, "reason": "ad"},
    )
    if not isinstance(payload, dict) or not str(payload.get("aweme_id") or "").strip():
        raise MediaRecordsRequestError("整篇广告记录接口缺少 aweme_id")
    return payload


def get_source_script_stats(
    *,
    collection_code: str,
    workflow: str,
    reservation_minutes: int = 120,
) -> dict:
    """统计财经口播稿总数、可用数、占用数和已使用数。"""
    payload = _request(
        "GET",
        "/v1/douyin-research/scripts/stats",
        query={
            "collection_code": collection_code,
            "workflow": workflow,
            "reservation_minutes": reservation_minutes,
        },
    )
    required_counts = ("total_count", "available_count", "reserved_count", "used_count")
    if not isinstance(payload, dict) or any(
        type(payload.get(name)) is not int or payload[name] < 0 for name in required_counts
    ):
        raise MediaRecordsRequestError("口播稿统计接口缺少有效的数量字段")
    if (
        not isinstance(payload.get("collection_code"), str)
        or not isinstance(payload.get("workflow"), str)
        or type(payload.get("reservation_minutes")) is not int
        or not isinstance(payload.get("checked_at"), str)
    ):
        raise MediaRecordsRequestError("口播稿统计接口缺少有效的查询信息")
    classified_count = sum(
        payload[name] for name in ("available_count", "reserved_count", "used_count")
    )
    if classified_count + int(payload.get("pending_editorial_count") or 0) != payload["total_count"]:
        raise MediaRecordsRequestError("口播稿统计接口返回的分类数量与总数不一致")
    return payload


def reserve_source_script(
    *,
    collection_code: str,
    workflow: str,
    reservation_minutes: int = 120,
) -> dict:
    """占用一条尚未使用的口播稿，供这次成片使用。"""
    payload = _request(
        "POST",
        "/v1/douyin-research/scripts/reserve",
        body={
            "collection_code": collection_code,
            "workflow": workflow,
            "reservation_minutes": reservation_minutes,
        },
    )
    if not isinstance(payload, dict):
        raise MediaRecordsRequestError("口播稿占用接口响应格式不正确")
    if not isinstance(payload.get("source"), dict) or not isinstance(payload.get("reservation"), dict):
        raise MediaRecordsRequestError("口播稿占用接口缺少 source 或 reservation 对象")
    return payload


def mark_source_script_used(
    *,
    aweme_id: str,
    workflow: str,
    reservation_token: str,
    run_id: str,
    source_hook: str,
) -> dict:
    """成片成功后，把这条口播稿标记为已使用。"""
    payload = _request(
        "POST",
        "/v1/douyin-research/scripts/used",
        body={
            "aweme_id": aweme_id,
            "workflow": workflow,
            "reservation_token": reservation_token,
            "run_id": run_id,
            "source_hook": source_hook,
        },
    )
    if not isinstance(payload, dict) or not isinstance(payload.get("record"), dict):
        raise MediaRecordsRequestError("口播稿已使用标记接口缺少 record 对象")
    return payload


def list_saved_shot_images() -> list[dict]:
    """返回已入库的财经镜头图。"""
    payload = _request("GET", "/v1/finance-generated-images")
    if not isinstance(payload, dict) or not isinstance(payload.get("records"), list):
        raise MediaRecordsRequestError("财经镜头图接口缺少 records 数组")
    return payload["records"]


def save_shot_images(records: list[dict]) -> dict:
    """把生成好的财经镜头图写入图库。"""
    payload = _request(
        "POST",
        "/v1/finance-generated-images/commit",
        body={"records": records},
    )
    if not isinstance(payload, dict) or not isinstance(payload.get("records"), list):
        raise MediaRecordsRequestError("财经镜头图写入接口缺少 records 数组")
    return payload
