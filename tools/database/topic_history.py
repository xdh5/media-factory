"""通过 Cloudflare D1 在时间窗口内做话题去重与占坑。"""

from __future__ import annotations

import hashlib
import re
import unicodedata

from .client import _request
from ._constants import DEFAULT_DEDUPLICATION_DAYS
from ._errors import DatabaseConflictError, DatabaseRequestError, TopicParameterError, DuplicateTopicError


def _validate_text(value: str, parameter: str) -> str:
    if not isinstance(value, str) or not value.strip():
        raise TopicParameterError(parameter, f"{parameter} 必须是非空字符串")
    return value.strip()


def _validate_days(days: int) -> int:
    if isinstance(days, bool) or not isinstance(days, int) or days < 1:
        raise TopicParameterError("days", "days 必须是大于等于 1 的整数")
    return days


def _fingerprint(topic: str) -> str:
    normalized = unicodedata.normalize("NFKC", topic).lower()
    normalized = re.sub(r"[^\w\u4e00-\u9fff]+", "", normalized)
    if not normalized:
        raise TopicParameterError("topic", "topic 规范化后为空，请提供包含文字或数字的话题")
    return hashlib.sha256(normalized.encode("utf-8")).hexdigest()


def list_recent_topics(workflow: str, days: int = DEFAULT_DEDUPLICATION_DAYS) -> list[dict]:
    """查询指定业务线近期占用的话题。"""
    payload = _request("GET", "/v1/topics", query={"workflow": _validate_text(workflow, "workflow"), "days": _validate_days(days)})
    return payload["records"]


def reserve_topic(workflow: str, topic: str, days: int = DEFAULT_DEDUPLICATION_DAYS) -> dict:
    """规范化话题指纹并原子占用话题。"""
    topic = _validate_text(topic, "topic")
    try:
        payload = _request("POST", "/v1/topics/reserve", body={
            "workflow": _validate_text(workflow, "workflow"), "topic": topic,
            "fingerprint": _fingerprint(topic), "days": _validate_days(days),
        })
    except DatabaseConflictError as exc:
        if exc.remote_code == "DUPLICATE_TOPIC":
            raise DuplicateTopicError(exc.message, exc.details) from exc
        raise
    return payload["record"]


def record_topic_usage(
    workflow: str, topic: str, publication_id: str, *,
    days: int = DEFAULT_DEDUPLICATION_DAYS, entries: list[dict] | None = None,
    history_days: int = 100, minimum_new_words: int = 5,
) -> dict:
    """幂等登记正式话题及可选词汇使用记录。"""
    topic = _validate_text(topic, "topic")
    try:
        return _request("POST", "/v1/publications/commit", body={
            "workflow": _validate_text(workflow, "workflow"), "topic": topic,
            "publication_id": _validate_text(publication_id, "publication_id"),
            "fingerprint": _fingerprint(topic), "days": _validate_days(days),
            "entries": entries or [], "history_days": _validate_days(history_days),
            "minimum_new_words": _validate_days(minimum_new_words),
        })
    except DatabaseConflictError as exc:
        if exc.remote_code == "DUPLICATE_TOPIC":
            raise DuplicateTopicError(exc.message, exc.details) from exc
        raise
