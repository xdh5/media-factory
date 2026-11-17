"""把公开抖音作品指标与财经定稿按发布记录关联。"""

from collections import Counter, defaultdict
from datetime import datetime

from core.tools.douyin_creator_works import read_creator_works
from core.tools.media_records import list_publication_records, list_publishing_account_groups

from ..config.settings import BEIJING_TIMEZONE
from ..infrastructure.source_scripts import list_used_editorial_drafts


def _title_key(title: str) -> str:
    return "".join(title.split())


def _public_work_identity(work: dict) -> tuple[str, datetime]:
    timestamp = (work.get("timer") or {}).get("public_time") or work["create_time"]
    return work.get("item_title") or work.get("desc") or "", datetime.fromtimestamp(timestamp, BEIJING_TIMEZONE)


def gather_douyin_works(progress=None) -> dict:
    """读取公开作品及原始指标，并返回每条作品匹配到的完整定稿。"""
    if progress:
        progress("正在用发布器读取财经抖音公开作品及详情")
    snapshot = read_creator_works("finance", metrics_only=True)
    observed_at = datetime.now(BEIJING_TIMEZONE)
    details = {str(item["id"]): item.get("metrics") or {}
               for response in snapshot["metrics"] for item in response["items"]}

    if progress:
        progress("正在关联财经发布记录和已使用定稿")
    records = list_publication_records(business_line="finance", platform="douyin")
    accounts = list_publishing_account_groups(business_line="finance")["members"]
    account_ids = {row["platform_account_id"] for row in accounts
                   if row["platform"] == "douyin" and row["display_name"] == "finance"}

    records_by_id = defaultdict(list)
    records_by_title_date = defaultdict(list)
    for record in records:
        if record["status"] not in {"published", "scheduled"}:
            continue
        if record["external_id"]:
            records_by_id[record["external_id"]].append(record)
        if record["account_id"] in account_ids:
            date = datetime.fromisoformat(record["publish_at"]).astimezone(BEIJING_TIMEZONE).date()
            records_by_title_date[(_title_key(record["title"]), date)].append(record)

    title_dates = Counter((_title_key(title), published_at.date())
                          for title, published_at in map(_public_work_identity, snapshot["works"]))
    works = []
    publications = {}
    for work in snapshot["works"]:
        work_id = str(work["aweme_id"])
        title, published_at = _public_work_identity(work)
        exact = records_by_id[work_id]
        title_date = (_title_key(title), published_at.date())
        same_title_and_date = records_by_title_date[title_date]
        candidates = exact or same_title_and_date
        match_type = "work_id" if exact else "title_and_beijing_date"
        distinct = {(record["publication_id"], record["content_part"]): record for record in candidates}
        match_status = "publication_missing"
        if len(distinct) > 1 or (not exact and same_title_and_date and title_dates[title_date] > 1):
            match_status = "publication_ambiguous"
        elif len(distinct) == 1:
            publications[work_id] = next(iter(distinct.values()))
            match_status = "draft_missing"
        works.append({
            "work_id": work_id,
            "title": title,
            "published_at": published_at.isoformat(),
            "duration_seconds": work["duration"] / 1000 if work.get("duration") else None,
            "statistics": work.get("statistics"),
            "metrics": details.get(work_id),
            "script": None,
            "match_status": match_status,
            "publication_match": match_type if work_id in publications else None,
        })

    run_ids = sorted({record["run_id"] for record in publications.values()})
    editorials = defaultdict(list)
    for start in range(0, len(run_ids), 100):
        for draft in list_used_editorial_drafts(run_ids[start:start + 100]):
            editorials[(draft["run_id"], _title_key(draft["editorial"]["title"]))].append(draft)

    for row in works:
        record = publications.get(row["work_id"])
        if record is None:
            continue
        candidates = editorials[(record["run_id"], _title_key(record["title"]))]
        if len(candidates) > 1:
            row["match_status"] = "draft_ambiguous"
        if len(candidates) != 1:
            continue
        draft = candidates[0]
        row["match_status"] = "matched"
        row["script"] = {
            "source_aweme_id": draft["aweme_id"],
            "run_id": record["run_id"],
            "content_part": record["content_part"],
            "editorial": draft["editorial"],
        }

    return {
        "account_group": "finance",
        "observed_at": observed_at.isoformat(),
        "public_works": len(works),
        "matched_scripts": sum(row["match_status"] == "matched" for row in works),
        "works": works,
    }
