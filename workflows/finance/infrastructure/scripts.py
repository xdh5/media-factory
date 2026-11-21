"""财经生产稿件领取、定稿读取与使用登记。"""

from __future__ import annotations

from tools.database._errors import DatabaseRequestError
from tools.database.client import _request


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
        raise DatabaseRequestError("口播稿占用接口响应格式不正确")
    if not isinstance(payload.get("source"), dict) or not isinstance(payload.get("reservation"), dict):
        raise DatabaseRequestError("口播稿占用接口缺少 source 或 reservation 对象")
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
        raise DatabaseRequestError("口播稿已使用标记接口缺少 record 对象")
    return payload


def list_editorial_drafts(missing_only: bool = True) -> dict:
    """只读返回未使用稿件及其定稿，不占用稿件。"""
    return _request("GET", "/v1/finance-editorial-drafts", query={"missing_only": str(missing_only).lower()})
