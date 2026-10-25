"""发布工具的精简响应，完整产物和任务明细按需读取。"""

from __future__ import annotations

from collections import Counter
from hashlib import blake2b


def account_groups_summary(payload: dict) -> dict:
    selected = {(member["platform"], member["account_ref"]) for group in payload["groups"] for member in group["members"]}
    required = {(group["name"], member["platform"], member["account_ref"])
                for group in payload["groups"] for member in group["members"]}
    verified = {(group["name"], account["platform"], account["account_ref"])
                for group in payload["groups"] for account in group["publisher_accounts"]
                if account["login_status"] == "connected"}
    ready = bool(required) and required.issubset(verified) and payload["publisher_error"] is None
    return {
        "all_accounts_ready": ready,
        "notice": "全部账号已登录，开始发布" if ready else "账号尚未全部通过，请先处理登录或检测问题",
        "groups": [
            {"name": group["name"], "business_line": group["business_line"], "enabled": group["enabled"],
             "platforms": [member["platform"] for member in group["members"]]}
            for group in payload["groups"]
        ],
        "login_states": [state for state in payload["publisher_login_states"]
                         if (state["platform"], state["account_ref"]) in selected],
        "error": payload["publisher_error"],
    }


def preview_summary(payload: dict) -> dict:
    return {
        **{key: payload[key] for key in ("business_line", "publish_date", "account_group", "platforms",
                                       "publishable_count", "duplicate_count", "timings_seconds", "reused_prepared")},
        "items": [{key: item[key] for key in ("production_id", "title", "content_kind", "content_part")}
                  for item in payload["items"]],
        "default_publication_plan": payload["default_publication_plan"],
        "default_schedule_skipped": payload["default_schedule_skipped"],
    }


def _publication_summary(published: list[dict]) -> dict:
    return {
        "scheduled_by_platform": dict(Counter(row["record"]["platform"] for row in published
                                               if row["record"]["status"] == "scheduled")),
        "published_by_platform": dict(Counter(row["record"]["platform"] for row in published
                                               if row["record"]["status"] == "published")),
        "records": [{key: row["record"].get(key) for key in ("id", "publication_id", "platform", "status", "external_url")}
                    for row in published],
    }


def task_summary(payload: dict, after_revision: str | None) -> dict:
    state = f"{payload['updated_at']}:{payload['status']}:{payload.get('progress') or ''}"
    revision = blake2b(state.encode(), digest_size=8).hexdigest()
    summary = {key: payload[key] for key in ("task_id", "status", "done", "duration_seconds")}
    summary["revision"] = revision
    if revision == after_revision:
        return {**summary, "changed": False}
    summary.update(changed=True, progress=payload["progress"])
    error = payload["error"]
    if error:
        summary["error"] = {key: error[key] for key in ("type", "message") if key in error}
        details = error.get("details")
        if details and "published" in details:
            summary["partial_result"] = {**_publication_summary(details["published"]),
                                         "failed": details["failed"], "timings_seconds": details["timings_seconds"]}
        elif details:
            summary["error"]["details"] = details
    result = payload["result"]
    if result:
        published = result["published"]
        summary["result"] = {
            "publish_date": result["publish_date"], "publish_at": result["publish_at"],
            **_publication_summary(published),
            "skipped_count": len(result["skipped"]),
            "timings_seconds": result.get("timings_seconds"),
        }
    return summary
