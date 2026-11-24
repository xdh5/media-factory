"""财经公共发布排期：每天北京时间18点一篇。"""

from datetime import datetime, timedelta
from zoneinfo import ZoneInfo

from ._constants import PLATFORM_ALIASES
from ._errors import InvalidPublishRequestError


def plan_finance_publications(
    tasks: list[dict], publish_date: str, publish_mode: str | None,
    publish_at: str | None, publish_at_by_platform: dict[str, str] | None,
    *, now: datetime | None = None,
) -> tuple[list[dict], list[dict]]:
    """默认每天安排第一篇，明确指定立即发布时保留用户选择。"""
    timezone = ZoneInfo("Asia/Shanghai")
    current = (now or datetime.now(timezone)).astimezone(timezone)
    mode = str(publish_mode or "").strip().lower()
    at = str(publish_at or "").strip()
    if mode and mode not in ("immediate", "scheduled"):
        raise InvalidPublishRequestError("publish_mode 只能是 immediate 或 scheduled")
    configured = {}
    selected_platforms = {task["route"]["platform"] for task in tasks}
    for key, value in (publish_at_by_platform or {}).items():
        platform = PLATFORM_ALIASES.get(str(key).strip().casefold())
        if platform not in selected_platforms:
            raise InvalidPublishRequestError(f"发布时间包含未选择的平台：{key}")
        configured[platform] = str(value or "").strip()
    groups = {}
    for task in tasks:
        route = task["route"]
        groups.setdefault((route["platform"], route["platform_account_id"]), []).append(task)
    planned, skipped = [], []
    for (platform, _), group in groups.items():
        group.sort(key=lambda t: (int(t["item"].get("content_part") or 1), t["item"]["production_id"]))
        override = configured.get(platform)
        explicit_at = override or at
        explicit_mode = ("immediate" if override.lower() == "now" else "scheduled") if override else mode
        if explicit_mode == "immediate":
            if explicit_at.lower() != "now":
                raise InvalidPublishRequestError("立即发布必须传 publish_at=now")
            chosen = {t["item"]["production_id"]: ("immediate", "now") for t in group}
        elif explicit_at:
            try:
                scheduled = datetime.fromisoformat(explicit_at.replace("Z", "+00:00"))
                if scheduled.tzinfo is None:
                    raise ValueError("缺少时区")
            except ValueError as extra:
                raise InvalidPublishRequestError("预约时间必须是带时区的 ISO 8601 时间") from extra
            item = group[0]
            chosen = {item["item"]["production_id"]: ("scheduled", explicit_at)}
        else:
            chosen = {}
            for task in group[:1]:
                hour = 18
                if platform == "toutiao" and hour == 18 and publish_date == (current.date() + timedelta(days=7)).isoformat():
                    hour = 17
                slot = datetime.fromisoformat(f"{publish_date}T{hour:02d}:00:00").replace(tzinfo=timezone)
                if slot > current:
                    chosen[task["item"]["production_id"]] = ("scheduled", slot.isoformat())
        for task in group:
            if task["already_published"]:
                continue
            timing = chosen.get(task["item"]["production_id"])
            if timing:
                planned.append({**task, "publish_mode": timing[0], "publish_at": timing[1]})
            else:
                skipped.append({
                    "production_id": task["item"]["production_id"], "platform": platform,
                    "account_id": task["route"]["platform_account_id"],
                    "reason": "默认每天一篇，或当天预约时段已过",
                })
    return planned, skipped
