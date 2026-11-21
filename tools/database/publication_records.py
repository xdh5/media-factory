"""数据库发布回执接口。"""

from .client import _request
from ._errors import DatabaseRequestError


def list_publication_records(
    *,
    business_line: str | None = None,
    platform: str | None = None,
    publish_date: str | None = None,
    run_id: str | None = None,
) -> list[dict]:
    query = {}
    if business_line:
        query["business_line"] = business_line
    if platform:
        query["platform"] = platform
    if publish_date:
        query["publish_date"] = publish_date
    if run_id:
        query["run_id"] = run_id
    payload = _request("GET", "/v1/publication-records", query=query)
    if not isinstance(payload, dict) or not isinstance(payload.get("records"), list):
        raise DatabaseRequestError("发布记录接口缺少 records 数组")
    return payload["records"]


def commit_publication_records(records: list[dict]) -> dict:
    payload = _request("POST", "/v1/publication-records/commit", body={"records": records})
    if not isinstance(payload, dict) or not isinstance(payload.get("records"), list):
        raise DatabaseRequestError("发布记录写入接口缺少 records 数组")
    return payload


def delete_publication_records(record_ids: list[int]) -> dict:
    """按数据库记录 ID 精确删除发布记录。"""
    payload = _request("DELETE", "/v1/publication-records", body={"record_ids": record_ids})
    if not isinstance(payload, dict) or not isinstance(payload.get("deleted_ids"), list):
        raise DatabaseRequestError("删除发布记录接口缺少 deleted_ids 数组")
    return payload
