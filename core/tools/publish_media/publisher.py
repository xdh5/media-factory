"""按日期选出成片并写入 D1。真正发到平台时调用 media-publisher 的 publishing。"""

from __future__ import annotations

import sys
import time
from concurrent.futures import ThreadPoolExecutor
from copy import deepcopy
from pathlib import Path

from core.tools.media_records import (
    commit_production_outputs,
    commit_publication_records,
    list_publication_records,
)
from core.tools.media_files import upload_public_file

from ._constants import PUBLIC_URL_PLATFORMS, media_publisher_root
from ._errors import DuplicatePublicationError, InvalidPublishRequestError, MediaPublisherCommandError
from .accounts import resolve_account_group
from .content import local_publish_items, normalize_platforms, normalize_publish_date
from .finance_schedule import plan_finance_publications

_PREPARED_PREVIEWS: dict[tuple, tuple[float, list]] = {}


def _measure_query(fn, *args, **kwargs):
    started = time.monotonic()
    value = fn(*args, **kwargs)
    return value, round(time.monotonic() - started, 3)


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
    production_id: str | None = None,
    reuse_prepared: bool = False,
) -> dict:
    started = time.monotonic()
    normalized_date = normalize_publish_date(publish_date)
    normalized_platforms = normalize_platforms(platforms)
    cache_key = (business_line, normalized_date, account_group, tuple(normalized_platforms), content_kind, production_id)
    cached = _PREPARED_PREVIEWS.get(cache_key) if reuse_prepared else None
    reused = bool(cached and time.monotonic() - cached[0] < 300
                  and all(Path(item["local_path"]).is_file() for item in cached[1]))
    # 所有目标账号通过真实页面检测后，才读取或恢复成片。
    routes, route_seconds = _measure_query(resolve_account_group, str(account_group).strip(), business_line, normalized_platforms)
    with ThreadPoolExecutor(max_workers=2) as queries:
        duplicate_query = queries.submit(_measure_query, _existing_keys, business_line, normalized_date)
        if reused:
            items = deepcopy(cached[1])
            item_seconds = 0.0
        else:
            item_query = queries.submit(_measure_query, local_publish_items, business_line, normalized_date, content_kind=content_kind)
            items, item_seconds = item_query.result()
        existing, duplicate_seconds = duplicate_query.result()
    if production_id:
        items = [item for item in items if item["production_id"] == production_id]
        if not items:
            raise InvalidPublishRequestError(f"找不到指定成片：{production_id}")
    _PREPARED_PREVIEWS[cache_key] = (time.monotonic(), deepcopy(items))
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
    default_plan, default_skipped = (plan_finance_publications(tasks, normalized_date, None, None, None)
                                     if business_line == "finance" else ([], []))
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
        "default_publication_plan": [
            {"production_id": t["item"]["production_id"], "content_part": t["item"].get("content_part", 1),
             "platform": t["route"]["platform"], "account_id": t["route"]["platform_account_id"],
             "publish_mode": t["publish_mode"], "publish_at": t["publish_at"]} for t in default_plan
        ],
        "default_schedule_skipped": default_skipped,
        "timings_seconds": {"items": item_seconds, "accounts": route_seconds, "duplicates": duplicate_seconds,
                            "total": round(time.monotonic() - started, 3)},
        "reused_prepared": reused,
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
    description = _publish_copy(item)
    target = {
        "platform": platform,
        "account_key": str(route.get("account_key") or f"{platform}:{route['platform_account_id']}"),
        "title": str(item["title"]),
        "description": description,
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


def _save_publication(task: dict, sent: dict, business_line: str) -> dict:
    item, route = task["item"], task["route"]
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
    return {"record": saved, "result": result}


def publish_local_outputs(
    business_line: str,
    publish_date: str,
    account_group: str,
    platforms: list[str],
    publish_mode: str | None,
    publish_at: str | None,
    *,
    content_kind: str | None = None,
    production_id: str | None = None,
    publish_at_by_platform: dict[str, str] | None = None,
    progress=None,
) -> dict:
    preview = preview_publication(
        business_line, publish_date, account_group, platforms, content_kind=content_kind,
        production_id=production_id,
        reuse_prepared=True,
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
    if business_line == "finance":
        pending, schedule_skipped = plan_finance_publications(
            preview["tasks"], preview["publish_date"], publish_mode, publish_at, publish_at_by_platform,
        )
        skipped.extend(schedule_skipped)
        if not pending:
            raise InvalidPublishRequestError("财经没有可预约的未来时段；北京时间 14 点、18 点各最多一篇，请明确其他时间或立即发布")
    language_timings = (normalize_publish_timings(preview["platforms"], publish_mode, publish_at, publish_at_by_platform)
                        if business_line != "finance" else {})
    # 先校验所有目标时间，避免发出第一篇后才发现下一篇的时间无效。
    for task in pending:
        task["timing"] = language_timings.get(task["route"]["platform"]) or normalize_publish_timings(
            [task["route"]["platform"]], task.get("publish_mode", publish_mode),
            task.get("publish_at", publish_at), None,
        )[task["route"]["platform"]]
    publish_batch, _, _ = _publishing()
    outcome = {"published": [], "failed": [], "publish_timings": {}}
    published = []
    target_timings = []
    for index, task in enumerate(pending, start=1):
        target_started = time.monotonic()
        try:
            route = task["route"]
            if progress:
                progress(f"正在发布 {index}/{len(pending)}：{route['platform']} - {task['item']['title']}")
            account_key = str(route.get("account_key") or f"{route['platform']}:{route['platform_account_id']}")
            batch_outcome = publish_batch(
                {
                    "account_group": str(account_group).strip(),
                    "publish_mode": task["timing"]["publish_mode"],
                    "publish_at": "now" if task["timing"]["publish_mode"] == "immediate" else task["timing"]["publish_at"],
                    "targets": [_target(task["item"], route)],
                },
                progress=None,
                account_routes={account_key: {**route, "account_group": route["account_ref"]}},
            )
            outcome["published"].extend(batch_outcome["published"])
            outcome["failed"].extend(batch_outcome["failed"])
            outcome["publish_timings"].update(batch_outcome["publish_timings"])
            for sent in batch_outcome["published"]:
                published.append(_save_publication(task, sent, business_line))
        except Exception as exc:
            outcome["failed"].append({"platform": task["route"]["platform"], "title": task["item"]["title"], "error": str(exc)})
        finally:
            target_timings.append({"platform": task["route"]["platform"], "production_id": task["item"]["production_id"],
                                   "seconds": round(time.monotonic() - target_started, 3)})
    if outcome["failed"]:
        detail = "；".join(
            f"{item.get('platform')} {item.get('title')}：{item.get('error')}" for item in outcome["failed"]
        )
        raise MediaPublisherCommandError(f"部分平台发布失败：{detail}",
                                         {"published": published, "failed": outcome["failed"],
                                          "timings_seconds": {"preview": preview["timings_seconds"], "targets": target_timings}})
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
        "publication_plan": [
            {"production_id": t["item"]["production_id"], "platform": t["route"]["platform"],
             "account_id": t["route"]["platform_account_id"], **t["timing"]}
            for t in pending
        ],
        "published": published,
        "skipped": skipped,
        "timings_seconds": {"preview": preview["timings_seconds"], "reused_prepared": preview["reused_prepared"],
                            "targets": target_timings},
    }
