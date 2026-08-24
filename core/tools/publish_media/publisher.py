"""统一执行官方平台和 MatrixMedia 视频发布，并逐条写入 D1。"""

from __future__ import annotations

from datetime import datetime
from pathlib import Path
from zoneinfo import ZoneInfo

from core.tools.cloudflare_data import (
    commit_production_outputs,
    commit_publication_records,
    list_publication_records,
)
from core.tools.publish_to_facebook import publish_to_facebook
from core.tools.publish_to_instagram import publish_to_instagram
from core.tools.publish_to_tiktok import publish_to_tiktok
from core.tools.publish_to_youtube import publish_to_youtube
from core.tools.r2_storage import upload_public_file

from ._constants import (
    BEIJING_TIMEZONE,
    MATRIXMEDIA_PLATFORM_CODES,
    PUBLIC_URL_PLATFORMS,
    PUBLISH_MODES,
)
from ._errors import DuplicatePublicationError, InvalidPublishRequestError, MatrixMediaCommandError
from .accounts import resolve_account_group, run_matrixmedia_cli
from .content import local_publish_items, normalize_platforms, normalize_publish_date


def normalize_publish_timing(publish_mode: str, publish_at: str) -> tuple[str, str | None]:
    mode = str(publish_mode or "").strip().casefold()
    raw = str(publish_at or "").strip()
    if mode not in PUBLISH_MODES:
        raise InvalidPublishRequestError(f"publish_mode 必须从 {PUBLISH_MODES} 中选择")
    if not raw:
        raise InvalidPublishRequestError("publish_at 不能为空；立即发布请明确填写 now，预约发布请填写带时区时间")
    now = datetime.now(ZoneInfo(BEIJING_TIMEZONE)).replace(microsecond=0)
    if mode == "immediate":
        if raw.casefold() != "now":
            raise InvalidPublishRequestError("立即发布时 publish_at 必须明确填写 now")
        return now.isoformat(), None
    try:
        scheduled = datetime.fromisoformat(raw.replace("Z", "+00:00"))
    except ValueError as exc:
        raise InvalidPublishRequestError(
            "预约发布的 publish_at 必须是带时区的 ISO 8601，例如 2026-08-26T16:00:00+08:00"
        ) from exc
    if scheduled.tzinfo is None or scheduled.utcoffset() is None:
        raise InvalidPublishRequestError("预约发布的 publish_at 必须包含时区，北京时间使用 +08:00")
    if scheduled <= now:
        raise InvalidPublishRequestError("预约发布时间已经过去；请改为 immediate + now，或指定未来时间")
    return scheduled.replace(microsecond=0).isoformat(), scheduled.astimezone(ZoneInfo(BEIJING_TIMEZONE)).strftime("%Y-%m-%d %H:%M:%S")


def _existing_keys(business_line: str, run_id: str) -> set[tuple]:
    return {
        (
            str(item.get("publication_id") or ""),
            str(item.get("platform") or ""),
            str(item.get("account_id") or ""),
            int(item.get("content_part") or 1),
        )
        for item in list_publication_records(business_line=business_line, run_id=run_id)
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
    existing = _existing_keys(business_line, str(items[0]["run_id"]))
    tasks = []
    for item in items:
        for route in routes:
            key = (
                str(item["production_id"]),
                str(route["platform"]),
                str(route["account_id"]),
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


def _publish_matrixmedia(item: dict, route: dict, scheduled_cli: str | None) -> dict:
    platform = str(route["platform"])
    arguments = [
        "publish", "-p", MATRIXMEDIA_PLATFORM_CODES[platform],
        "-f", str(item["local_path"]), "--title", str(item["title"]),
        "--name", str(item["title"]), "--phone", str(route["account_id"]),
        "--creative-statement", "ai_generated",
    ]
    short_title = str(item.get("short_title") or "").strip()
    if platform == "wechat_channels":
        if not short_title:
            raise InvalidPublishRequestError("视频号发布需要本地产物目录中的 short-title.txt")
        arguments.extend(["--bt2", short_title])
    if scheduled_cli:
        arguments.extend(["--publish-at", scheduled_cli])
    payload = run_matrixmedia_cli(arguments)
    if not isinstance(payload, dict):
        raise MatrixMediaCommandError("MatrixMedia 发布结果不是 JSON 对象")
    status = str(payload.get("status") or payload.get("resultStatus") or "success")
    if status in {"needs_attention", "failed", "failure"}:
        raise MatrixMediaCommandError(f"MatrixMedia 发布未成功：{payload.get('message') or status}")
    return payload


def _publish_official(item: dict, route: dict, publish_at: str | None) -> dict:
    platform = str(route["platform"])
    title = str(item["title"])
    copy = str(item.get("publish_copy") or title)
    if platform == "youtube":
        return publish_to_youtube(
            str(route["account_id"]), item["local_path"], title,
            description=copy, account=str(route.get("account_ref") or ""),
            privacy_status="public", publish_at=publish_at,
        )
    video_url = _public_video_url(item)
    if platform == "tiktok":
        return publish_to_tiktok(
            str(route["account_id"]), video_url, copy,
            account=str(route.get("account_ref") or ""), publish_at=publish_at,
        )
    if platform == "instagram":
        return publish_to_instagram(str(route["account_id"]), video_url, copy, publish_at=publish_at)
    if platform == "facebook":
        return publish_to_facebook(str(route["account_id"]), video_url, copy, title=title, publish_at=publish_at)
    raise InvalidPublishRequestError(f"平台 {platform} 没有可用的官方发布实现")


def publish_local_outputs(
    business_line: str,
    publish_date: str,
    account_group: str,
    platforms: list[str],
    publish_mode: str,
    publish_at: str,
    *,
    content_kind: str | None = None,
    progress=None,
) -> dict:
    effective_at, scheduled_cli = normalize_publish_timing(publish_mode, publish_at)
    preview = preview_publication(
        business_line, publish_date, account_group, platforms, content_kind=content_kind,
    )
    pending = [task for task in preview["tasks"] if not task["already_published"]]
    skipped = [
        {
            "production_id": task["item"]["production_id"],
            "platform": task["route"]["platform"],
            "account_id": task["route"]["account_id"],
            "reason": "数据库已有相同产物、平台、账号和分段的发布记录",
        }
        for task in preview["tasks"] if task["already_published"]
    ]
    if not pending:
        raise DuplicatePublicationError("所选内容在目标账号和平台都已经发布或预约，无需重复发送")
    published = []
    for index, task in enumerate(pending, start=1):
        item, route = task["item"], task["route"]
        if progress:
            progress(f"正在发布 {index}/{len(pending)}：{route['platform']} - {item['title']}")
        connector = str(route["connector"])
        result = (
            _publish_matrixmedia(item, route, scheduled_cli)
            if connector == "matrixmedia"
            else _publish_official(item, route, None if publish_mode == "immediate" else effective_at)
        )
        external_id = str(result.get("video_id") or result.get("post_id") or result.get("id") or "")
        external_url = str(result.get("video_url") or result.get("platform_url") or result.get("url") or "")
        record = {
            "publication_id": str(item["production_id"]),
            "run_id": str(item["run_id"]),
            "business_line": business_line,
            "platform": str(route["platform"]),
            "connector": connector,
            "account_id": str(route["account_id"]),
            "content_part": int(item.get("content_part") or 1),
            "title": str(item["title"]),
            "publish_mode": publish_mode,
            "publish_at": effective_at if publish_mode == "scheduled" else datetime.now(ZoneInfo(BEIJING_TIMEZONE)).replace(microsecond=0).isoformat(),
            "status": "scheduled" if publish_mode == "scheduled" else "published",
            "external_id": external_id or None,
            "external_url": external_url or None,
        }
        saved = commit_publication_records([record])["records"][0]
        published.append({"record": saved, "result": result})
    return {
        "business_line": business_line,
        "publish_date": preview["publish_date"],
        "publish_mode": publish_mode,
        "publish_at": effective_at,
        "published": published,
        "skipped": skipped,
    }
