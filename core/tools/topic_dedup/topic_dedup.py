"""通过 Cloudflare D1 在时间窗口内做话题去重与占坑。"""

from __future__ import annotations

import hashlib
import re
import unicodedata

from core.tools.cloudflare_data import (
    CloudflareDataConflictError,
    CloudflareDataError,
    list_topics,
    reserve_topic,
)

from ._constants import DEFAULT_DEDUPLICATION_DAYS
from ._errors import DuplicateTopicError, InvalidParameterError, TopicDataServiceError

__all__ = ["get_topic", "update"]


def _validate_text(value: str, parameter: str) -> str:
    if not isinstance(value, str) or not value.strip():
        raise InvalidParameterError(parameter, f"{parameter} 必须是非空字符串")
    return value.strip()


def _validate_days(days: int) -> int:
    if isinstance(days, bool) or not isinstance(days, int) or days < 1:
        raise InvalidParameterError("days", "days 必须是大于等于 1 的整数")
    return days


def _fingerprint(topic: str) -> str:
    normalized = unicodedata.normalize("NFKC", topic).lower()
    normalized = re.sub(r"[^\w\u4e00-\u9fff]+", "", normalized)
    if not normalized:
        raise InvalidParameterError("topic", "topic 规范化后为空，请提供包含文字或数字的话题")
    return hashlib.sha256(normalized.encode("utf-8")).hexdigest()


def get_topic(workflow: str, days: int = DEFAULT_DEDUPLICATION_DAYS) -> list[dict]:
    """返回指定工作流最近 days 天内已占用的话题。"""
    normalized_workflow = _validate_text(workflow, "workflow")
    window_days = _validate_days(days)
    try:
        return list_topics(normalized_workflow, window_days)
    except CloudflareDataError as exc:
        raise TopicDataServiceError(
            f"读取 Cloudflare D1 最近话题失败：{exc.message}",
            exc.details,
        ) from exc


def update(workflow: str, topic: str, days: int = DEFAULT_DEDUPLICATION_DAYS) -> dict:
    """在 Cloudflare D1 原子写入一个未在时间窗口内重复的话题。"""
    normalized_workflow = _validate_text(workflow, "workflow")
    normalized_topic = _validate_text(topic, "topic")
    window_days = _validate_days(days)
    try:
        return reserve_topic(
            normalized_workflow,
            normalized_topic,
            _fingerprint(normalized_topic),
            window_days,
        )
    except CloudflareDataConflictError as exc:
        if exc.remote_code == "DUPLICATE_TOPIC":
            raise DuplicateTopicError(exc.message, exc.details) from exc
        raise TopicDataServiceError(exc.message, exc.details) from exc
    except CloudflareDataError as exc:
        raise TopicDataServiceError(
            f"写入 Cloudflare D1 话题失败：{exc.message}",
            exc.details,
        ) from exc
