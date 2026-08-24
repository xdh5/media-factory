"""按计划发布日期读取本地生产记录和实际成片。"""

from __future__ import annotations

from datetime import date

from core.tools.cloudflare_data import list_production_outputs

from ._constants import BUSINESS_LINES, PLATFORM_ALIASES, SUPPORTED_PLATFORMS
from ._errors import InvalidPublishRequestError, PublishContentNotFoundError
from .local_assets import ensure_local_publish_items, enrich_local_publish_item


def normalize_publish_date(value: str) -> str:
    text = str(value or "").strip()
    if not text:
        raise InvalidPublishRequestError("publish_date 不能为空；请先向用户确认要发布哪一天的产物")
    try:
        return date.fromisoformat(text).isoformat()
    except ValueError as exc:
        raise InvalidPublishRequestError("publish_date 必须是 YYYY-MM-DD，例如 2026-08-25") from exc


def normalize_platforms(values: list[str]) -> list[str]:
    platforms = []
    for raw in values or []:
        key = str(raw or "").strip().casefold()
        platform = PLATFORM_ALIASES.get(key)
        if not platform or platform not in SUPPORTED_PLATFORMS:
            raise InvalidPublishRequestError(f"不支持的发布平台：{raw}")
        if platform not in platforms:
            platforms.append(platform)
    if not platforms:
        raise InvalidPublishRequestError("platforms 至少要指定一个平台")
    return platforms


def local_publish_items(
    business_line: str,
    publish_date: str,
    *,
    content_kind: str | None = None,
) -> list[dict]:
    if business_line not in BUSINESS_LINES:
        raise InvalidPublishRequestError(f"business_line 必须从 {BUSINESS_LINES} 中选择")
    normalized_date = normalize_publish_date(publish_date)
    ensure_local_publish_items(business_line, normalized_date, content_kind=content_kind)
    rows = list_production_outputs(
        publish_date=normalized_date,
        business_line=business_line,
        source="local_mcp",
    )
    wanted_kind = str(content_kind or "").strip()
    if wanted_kind:
        rows = [item for item in rows if str(item.get("content_kind") or "") == wanted_kind]
    items = []
    for row in rows:
        enriched = enrich_local_publish_item(row)
        if enriched:
            items.append(enriched)
    if not items:
        suffix = f"、内容类型 {wanted_kind}" if wanted_kind else ""
        raise PublishContentNotFoundError(
            f"找不到 {normalized_date} 的 {business_line} 本地产物{suffix}；只允许发布已经写入 production_outputs 且文件仍存在的 local_mcp 成片",
            {"business_line": business_line, "publish_date": normalized_date, "content_kind": wanted_kind},
        )
    return sorted(items, key=lambda item: (str(item.get("content_kind")), int(item.get("content_part") or 1)))
