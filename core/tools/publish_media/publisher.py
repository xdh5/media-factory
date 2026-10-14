"""按日期选出成片并写入 D1。真正发到平台时调用 media-publisher 的 publishing。"""

from __future__ import annotations

import sys
from pathlib import Path

from core.tools.cloudflare_data import (
    commit_production_outputs,
    commit_publication_records,
    list_publication_records,
)
from core.tools.r2_storage import upload_public_file

from ._constants import PUBLIC_URL_PLATFORMS, media_publisher_root
from ._errors import DuplicatePublicationError, InvalidPublishRequestError, MediaPublisherCommandError
from .accounts import resolve_account_group
from .content import local_publish_items, normalize_platforms, normalize_publish_date


def _publishing():
    """加载 media-publisher 的 python/publishing。两个 MCP 的平台发布都走这一份。"""
    root = media_publisher_root()
    python_dir = root / "python"
    text = str(python_dir)
    if text not in sys.path:
        sys.path.insert(0, text)
    try:
        from publishing.batch import publish_batch
        from publishing.platforms import PublishError
        from publishing.schedule import resolve_timings
    except ImportError as exc:
        raise MediaPublisherCommandError(f"无法加载 media-publisher 统一发布：{exc}", {"media_publisher_dir": str(root)}) from exc
    return publish_batch, resolve_timings, PublishError


def normalize_publish_timings(
    platforms: list[str],
    publish_mode: str | None,
    publish_at: str | None,
    publish_at_by_platform: dict[str, str] | None,
) -> dict[str, dict[str, str | None]]:
    """解析各平台发布时间。规则与 media-publisher MCP 使用同一份 publishing。"""
    _, resolve_timings, publish_error = _publishing()
    from publishing.platforms import resolve_platform

    try:
        specs = [resolve_platform(item) for item in platforms]
        timings = resolve_timings(specs, publish_mode, publish_at, publish_at_by_platform)
    except publish_error as exc:
        raise InvalidPublishRequestError(str(exc)) from exc
    return {
        platform: {
            "publish_mode": item["publish_mode"],
            "publish_at": item["publish_at"],
            "scheduled_cli": item["cli_publish_at"],
        }
        for platform, item in timings.items()
    }


def _content_key(title: str, platform: str, account_id: str, content_part: int) -> tuple:
    """在指定业务线和生产批次内生成与 D1 唯一索引一致的内容键。"""
    return (
        str(title).strip(),
        str(platform).strip(),
        str(account_id).strip(),
        int(content_part or 1),
    )


def _existing_keys(business_line: str, publish_date: str) -> set[tuple]:
    return {
        _content_key(
            str(item.get("title") or ""),
            str(item.get("platform") or ""),
            str(item.get("account_id") or ""),
            int(item.get("content_part") or 1),
        )
        for item in list_publication_records(business_line=business_line, run_id=f"run-{publish_date.replace('-', '')}")
    }


def preview_publication(
    business_line: str,
    publish_date: str,
    account_group: str,
    platforms: list[str],
    *,
    content_kind: str | None = None,
) -> dict:
    normalized_date = normalize_publish_date(publish_date)
    normalized_platforms = normalize_platforms(platforms)
    items = local_publish_items(business_line, normalized_date, content_kind=content_kind)
    routes = resolve_account_group(str(account_group).strip(), business_line, normalized_platforms)
    existing = _existing_keys(business_line, normalized_date)
    tasks = []
    for item in items:
        for route in routes:
            key = _content_key(
                str(item["title"]),
                str(route["platform"]),
                str(route["platform_account_id"]),
                int(item.get("content_part") or 1),
            )
            tasks.append({"item": item, "route": route, "already_published": key in existing})
    return {
        "business_line": business_line,
        "publish_date": normalized_date,
        "account_group": str(account_group).strip(),
        "platforms": normalized_platforms,
        "items": items,
        "routes": routes,
        "tasks": tasks,
        "publishable_count": sum(not task["already_published"] for task in tasks),
        "duplicate_count": sum(task["already_published"] for task in tasks),
    }


def _public_video_url(item: dict) -> str:
    existing = str(item.get("r2_url") or "").strip()
    if existing:
        return existing
    local_path = Path(item["local_path"])
    remote = upload_public_file(
        local_path,
        f"runs/{item['business_line']}/{item['run_id']}/publish/{local_path.name}",
        content_type="video/mp4",
    )
    url = str(remote["url"])
    commit_production_outputs([{**item, "r2_url": url}])
    item["r2_url"] = url
    return url


def _publish_copy(item: dict) -> str:
    content_kind = str(item.get("content_kind") or "").strip()
    if content_kind.startswith("en-ko"):
        return str(item.get("publish_copy") or item.get("hashtags") or "").strip()
    return str(item.get("publish_copy") or item["title"]).strip()


def _target(item: dict, route: dict) -> dict:
    platform = str(route["platform"])
    target = {
        "platform": platform,
        "title": str(item["title"]),
        "description": _publish_copy(item),
        "file": str(item["local_path"]),
        "tags": str(item.get("hashtags") or "").strip(),
        "bt2": str(item.get("short_title") or "").strip(),
        "publication_id": str(item["production_id"]),
        "client_ref": str(item["production_id"]),
        "creative_statement": "ai_generated",
    }
    if platform in PUBLIC_URL_PLATFORMS:
        target["video_url"] = _public_video_url(item)
    return target


def publish_local_outputs(
    business_line: str,
    publish_date: str,
    account_group: str,
    platforms: list[str],
    publish_mode: str | None,
    publish_at: str | None,
    *,
    content_kind: str | None = None,
    publish_at_by_platform: dict[str, str] | None = None,
    progress=None,
) -> dict:
    preview = preview_publication(
        business_line, publish_date, account_group, platforms, content_kind=content_kind,
    )
    timings = normalize_publish_timings(
        preview["platforms"], publish_mode, publish_at, publish_at_by_platform,
    )
    pending = [task for task in preview["tasks"] if not task["already_published"]]
    skipped = [
        {
            "production_id": task["item"]["production_id"],
            "platform": task["route"]["platform"],
            "account_id": task["route"]["platform_account_id"],
            "reason": "数据库已有相同产物、平台、账号和分段的发布记录",
        }
        for task in preview["tasks"] if task["already_published"]
    ]
    if not pending:
        raise DuplicatePublicationError("所选内容在目标账号和平台都已经发布或预约，无需重复发送")
    publish_batch, _, publish_error = _publishing()
    from publishing.platforms import resolve_platform

    pending_codes = {resolve_platform(str(task["route"]["platform"])).code for task in pending}
    platform_times = {}
    for key, value in (publish_at_by_platform or {}).items():
        code = resolve_platform(str(key)).code
        if code in pending_codes:
            platform_times[code] = value
    try:
        outcome = publish_batch(
            {
                "account_group": str(account_group).strip(),
                "publish_mode": publish_mode,
                "publish_at": publish_at,
                "publish_at_by_platform": platform_times,
                "targets": [_target(task["item"], task["route"]) for task in pending],
            },
            progress=progress,
        )
    except publish_error as exc:
        raise InvalidPublishRequestError(str(exc)) from exc
    published_by_key = {
        (str(item.get("client_ref") or ""), str(item.get("platform") or "")): item
        for item in outcome["published"]
    }
    published = []
    for task in pending:
        item, route = task["item"], task["route"]
        sent = published_by_key.get((str(item["production_id"]), str(route["platform"])))
        if sent is None:
            continue
        result = sent.get("result") if isinstance(sent.get("result"), dict) else {}
        external_id = str(result.get("video_id") or result.get("post_id") or result.get("id") or "")
        external_url = str(result.get("video_url") or result.get("platform_url") or result.get("url") or "")
        record = {
            "publication_id": str(item["production_id"]),
            "run_id": str(item["run_id"]),
            "business_line": business_line,
            "platform": str(route["platform"]),
            "connector": str(route["connector"]),
            "account_id": str(route["platform_account_id"]),
            "content_part": int(item.get("content_part") or 1),
            "title": str(item["title"]),
            "publish_mode": sent["publish_mode"],
            "publish_at": sent["publish_at"],
            "status": "scheduled" if sent["publish_mode"] == "scheduled" else "published",
            "external_id": external_id or None,
            "external_url": external_url or None,
        }
        saved = commit_publication_records([record])["records"][0]
        published.append({"record": saved, "result": result})
    if outcome["failed"]:
        detail = "；".join(
            f"{item.get('platform')} {item.get('title')}：{item.get('error')}" for item in outcome["failed"]
        )
        raise MediaPublisherCommandError(f"部分平台发布失败：{detail}")
    timings = {
        platform: {
            "publish_mode": item["publish_mode"],
            "publish_at": item["publish_at"],
            "scheduled_cli": item["cli_publish_at"],
        }
        for platform, item in outcome["publish_timings"].items()
    }
    return {
        "business_line": business_line,
        "publish_date": preview["publish_date"],
        "publish_mode": (
            next(iter({str(item["publish_mode"]) for item in timings.values()}))
            if len({str(item["publish_mode"]) for item in timings.values()}) == 1
            else "per_platform"
        ),
        "publish_at": str(publish_at or "per_platform"),
        "publish_timings": timings,
        "published": published,
        "skipped": skipped,
    }
