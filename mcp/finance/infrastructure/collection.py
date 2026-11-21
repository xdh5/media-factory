"""财经作者管理、原稿采集、审核定稿与数据查询。"""

from tools.database._errors import DatabaseRequestError
from tools.database.client import _request


def list_source_authors() -> list[dict]:
    """按添加顺序返回财经作者名单。"""
    payload = _request("GET", "/v1/finance-source-authors")
    if not isinstance(payload, dict) or not isinstance(payload.get("authors"), list):
        raise DatabaseRequestError("财经作者名单接口缺少 authors 数组")
    authors = []
    for item in payload["authors"]:
        if not isinstance(item, dict):
            raise DatabaseRequestError("财经作者名单包含无效记录")
        sec_user_id = str(item.get("sec_user_id") or "").strip()
        profile_url = str(item.get("profile_url") or "").strip()
        if not sec_user_id or not profile_url:
            raise DatabaseRequestError("财经作者名单缺少主页标识")
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
        raise DatabaseRequestError("财经作者写入接口缺少 author")
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
        raise DatabaseRequestError("财经作者删除接口缺少 author")
    return author


def list_saved_script_ids() -> list[str]:
    """返回已经入库的口播稿作品 ID，抓取时用来去重。"""
    payload = _request("GET", "/v1/douyin-research/ids")
    if not isinstance(payload, dict) or not isinstance(payload.get("aweme_ids"), list):
        raise DatabaseRequestError("已入库口播稿接口缺少 aweme_ids 数组")
    return [str(value) for value in payload["aweme_ids"] if str(value).strip()]


def save_transcribed_scripts(records: list[dict]) -> dict:
    """把转写完成的口播稿写入财经稿件库。"""
    payload = _request(
        "POST",
        "/v1/douyin-research/commit",
        body={"records": records},
    )
    if not isinstance(payload, dict) or not isinstance(payload.get("records"), list):
        raise DatabaseRequestError("转写稿写入接口缺少 records 数组")
    return payload


def list_rejected_video_ids() -> list[str]:
    """返回已弃用的作品 ID，避免下次重复下载。"""
    payload = _request("GET", "/v1/finance-rejected-awemes")
    if not isinstance(payload, dict) or not isinstance(payload.get("aweme_ids"), list):
        raise DatabaseRequestError("弃稿查询接口缺少 aweme_ids 数组")
    return [str(value) for value in payload["aweme_ids"] if str(value).strip()]


def record_collection_review(record: dict) -> dict:
    """按作品保存审核结果，供统计和后续采集去重。"""
    return _request("POST", "/v1/finance-collection-reviews", body=record)


def get_collection_review_stats() -> dict:
    """读取采集审核量、弃稿率、原因和作者来源。"""
    return _request("GET", "/v1/finance-collection-reviews")


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
        raise DatabaseRequestError("口播稿统计接口缺少有效的数量字段")
    if (
        not isinstance(payload.get("collection_code"), str)
        or not isinstance(payload.get("workflow"), str)
        or type(payload.get("reservation_minutes")) is not int
        or not isinstance(payload.get("checked_at"), str)
    ):
        raise DatabaseRequestError("口播稿统计接口缺少有效的查询信息")
    classified_count = sum(
        payload[name] for name in ("available_count", "reserved_count", "used_count")
    )
    if classified_count + int(payload.get("pending_editorial_count") or 0) != payload["total_count"]:
        raise DatabaseRequestError("口播稿统计接口返回的分类数量与总数不一致")
    return payload


def list_saved_shot_images() -> list[dict]:
    """返回已入库的财经镜头图。"""
    payload = _request("GET", "/v1/finance-generated-images")
    if not isinstance(payload, dict) or not isinstance(payload.get("records"), list):
        raise DatabaseRequestError("财经镜头图接口缺少 records 数组")
    return payload["records"]


def save_shot_images(records: list[dict]) -> dict:
    """把生成好的财经镜头图写入图库。"""
    payload = _request(
        "POST",
        "/v1/finance-generated-images/commit",
        body={"records": records},
    )
    if not isinstance(payload, dict) or not isinstance(payload.get("records"), list):
        raise DatabaseRequestError("财经镜头图写入接口缺少 records 数组")
    return payload


def list_used_editorial_drafts(run_ids: list[str]) -> list[dict]:
    """按生产批次读取已使用的财经定稿。"""
    payload = _request(
        "GET", "/v1/finance-editorial-drafts/used",
        query={"run_ids": ",".join(run_ids)},
    )
    if not isinstance(payload, dict) or not isinstance(payload.get("records"), list):
        raise DatabaseRequestError("已使用定稿接口缺少 records 数组")
    return payload["records"]


def list_scenario_quiz_questions(*, days: int = 30) -> list[dict]:
    payload = _request("GET", "/v1/scenario-quiz-questions", query={"days": days})
    if not isinstance(payload, dict) or not isinstance(payload.get("records"), list):
        raise DatabaseRequestError("情境测试题库接口缺少 records 数组")
    return payload["records"]


def commit_scenario_quiz_question(record: dict) -> dict:
    payload = _request("POST", "/v1/scenario-quiz-questions/commit", body={"record": record})
    if not isinstance(payload, dict) or not isinstance(payload.get("record"), dict):
        raise DatabaseRequestError("情境测试题库写入接口缺少 record 对象")
    return payload["record"]


def write_editorial_drafts(records: list[dict]) -> dict:
    """保存已经完成校验的财经定稿。"""
    return _request("POST", "/v1/finance-editorial-drafts", body={"records": records})
