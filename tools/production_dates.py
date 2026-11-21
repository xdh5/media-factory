"""生产计划日期校验与批次日期转换。"""

from datetime import date, datetime
from zoneinfo import ZoneInfo

BEIJING_TIMEZONE = ZoneInfo("Asia/Shanghai")


def normalize_publish_date(publish_date: str) -> str:
    """校验北京时间计划发布日期，返回 YYYY-MM-DD。"""
    value = str(publish_date or "").strip()
    try:
        resolved = date.fromisoformat(value)
    except ValueError as exc:
        raise ValueError("publish_date 必须是 YYYY-MM-DD，例如 2026-08-25") from exc
    today = datetime.now(BEIJING_TIMEZONE).date()
    if resolved < today:
        raise ValueError(f"publish_date 不能早于北京时间当天 {today.isoformat()}")
    return resolved.isoformat()


def production_run_id(publish_date: str) -> str:
    """按北京时间计划发布日期生成 run-YYYYMMDD。"""
    normalized = normalize_publish_date(publish_date)
    return f"run-{normalized.replace('-', '')}"


def publish_date_from_run_id(run_id: str) -> str:
    """从新格式 run-YYYYMMDD 还原北京时间计划发布日期。"""
    value = str(run_id or "").strip()
    if len(value) != 12 or not value.startswith("run-") or not value[4:].isdigit():
        raise ValueError("run_id 必须是 run-YYYYMMDD，例如 run-20260825")
    raw = value[4:]
    try:
        return date(int(raw[:4]), int(raw[4:6]), int(raw[6:8])).isoformat()
    except ValueError as exc:
        raise ValueError(f"run_id 包含无效日期：{value}") from exc
