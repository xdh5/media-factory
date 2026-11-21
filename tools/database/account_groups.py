"""数据库账号组接口。"""

from .client import _request
from ._errors import DatabaseRequestError


def list_publishing_account_groups(*, business_line: str | None = None) -> dict:
    query = {"business_line": business_line} if business_line else None
    payload = _request("GET", "/v1/publishing-account-groups", query=query)
    if (
        not isinstance(payload, dict)
        or not isinstance(payload.get("groups"), list)
        or not isinstance(payload.get("members"), list)
    ):
        raise DatabaseRequestError("发布账号组接口缺少 groups 或 members 数组")
    return payload
