"""语言词包与词汇历史的数据接口。"""

from tools.database._errors import DatabaseRequestError
from tools.database.client import _request


def list_recent_words(days: int) -> list[str]:
    payload = _request("GET", "/v1/words/recent", query={"days": days})
    if not isinstance(payload, dict) or not isinstance(payload.get("words"), list):
        raise DatabaseRequestError("单词历史接口缺少 words 数组")
    return [str(item) for item in payload["words"]]


def list_language_learning_pack_topics() -> list[str]:
    """读取 D1 中所有已入库预制图包的主题。"""
    payload = _request("GET", "/v1/language-learning-packs/topics")
    if not isinstance(payload, dict) or not isinstance(payload.get("topics"), list):
        raise DatabaseRequestError("语言词包主题接口缺少 topics 数组")
    return payload["topics"]


def commit_language_learning_pack(pack: dict) -> dict:
    """写入一个已验收的语言学习词包。"""
    payload = _request("POST", "/v1/language-learning-packs/commit", body={"pack": pack})
    if not isinstance(payload, dict) or not isinstance(payload.get("pack"), dict):
        raise DatabaseRequestError("语言词包写入接口缺少 pack 对象")
    return payload["pack"]


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


def validate_and_record_words(
    *,
    workflow: str,
    run_id: str,
    topic: str,
    entries: list[dict],
    history_days: int,
    minimum_new_words: int,
) -> dict:
    payload = _request(
        "POST",
        "/v1/words/validate-and-record",
        body={
            "workflow": workflow,
            "run_id": run_id,
            "topic": topic,
            "entries": entries,
            "history_days": history_days,
            "minimum_new_words": minimum_new_words,
        },
    )
    if not isinstance(payload, dict):
        raise DatabaseRequestError("单词历史接口响应格式不正确")
    return payload
