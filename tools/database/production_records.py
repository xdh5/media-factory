"""数据库成片记录接口。"""

from .client import _request
from ._errors import DatabaseRequestError


def list_production_outputs(
    *,
    publish_date: str | None = None,
    business_line: str | None = None,
    source: str | None = None,
) -> list[dict]:
    query = {}
    if publish_date:
        query["publish_date"] = publish_date
    if business_line:
        query["business_line"] = business_line
    if source:
        query["source"] = source
    payload = _request("GET", "/v1/production-outputs", query=query)
    if not isinstance(payload, dict) or not isinstance(payload.get("records"), list):
        raise DatabaseRequestError("产物记录接口缺少 records 数组")
    return payload["records"]


def delete_production_outputs(record_ids: list[int]) -> dict:
    """按精确记录 ID 删除成片记录。"""
    payload = _request("DELETE", "/v1/production-outputs", body={"record_ids": record_ids})
    if not isinstance(payload, dict) or not isinstance(payload.get("deleted_ids"), list):
        raise DatabaseRequestError("删除产物记录接口缺少 deleted_ids 数组")
    return payload


def commit_production_outputs(records: list[dict]) -> dict:
    payload = _request("POST", "/v1/production-outputs/commit", body={"records": records})
    if not isinstance(payload, dict) or not isinstance(payload.get("records"), list):
        raise DatabaseRequestError("产物记录写入接口缺少 records 数组")
    return payload
