"""计划发布日期解析；仅标准库，供 GitHub Actions plan job 使用。"""

from __future__ import annotations

from datetime import date, datetime, timedelta
from zoneinfo import ZoneInfo


def resolve_publish_date(value: str = "", default_days_ahead: int = 0) -> str:
    """解析计划发布日期；留空时按北京时间当天加指定天数，禁止选择过去日期。"""
    today = datetime.now(ZoneInfo("Asia/Shanghai")).date()
    text = str(value or "").strip()
    if not text:
        if default_days_ahead not in (0, 1):
            raise ValueError("default_days_ahead 只能是 0 或 1")
        return (today + timedelta(days=default_days_ahead)).isoformat()
    try:
        resolved = date.fromisoformat(text)
    except ValueError as exc:
        raise ValueError("publish_date 必须是 YYYY-MM-DD，例如 2026-08-25") from exc
    if resolved < today:
        raise ValueError(f"publish_date 不能早于北京时间当天 {today.isoformat()}")
    return resolved.isoformat()
