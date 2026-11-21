"""语言生产领取与归还词包的数据接口。"""

from tools.database._errors import DatabaseRequestError
from tools.database.client import _request


def claim_language_learning_pack(*, run_id: str, publish_date: str) -> dict:
    """为 GitHub 生产原子领取一个未使用语言词包。"""
    payload = _request(
        "POST", "/v1/language-learning-packs/claim",
        body={"run_id": run_id, "publish_date": publish_date},
    )
    if not isinstance(payload, dict) or not isinstance(payload.get("pack"), dict):
        raise DatabaseRequestError("语言词包领取接口缺少 pack 对象")
    return payload["pack"]


def release_language_learning_pack(*, run_id: str, publish_date: str) -> dict:
    """归还失败生产任务占用的语言词包。"""
    return _request("POST", "/v1/language-learning-packs/release", body={"run_id": run_id, "publish_date": publish_date})
