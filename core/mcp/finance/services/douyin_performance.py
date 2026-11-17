"""把公开抖音作品指标与财经定稿按发布记录关联。"""

from collections import Counter, defaultdict
from datetime import datetime, timedelta
from math import isfinite
from pathlib import Path

from core.tools.douyin_creator_works import read_creator_works
from core.tools.media_records import list_publication_records, list_publishing_account_groups

from ..config.settings import BEIJING_TIMEZONE
from ..infrastructure.source_scripts import list_used_editorial_drafts
from .prompts import read_prompt


ANALYSIS_PROMPT_PATH = Path(__file__).resolve().parents[1] / "prompts" / "douyin-performance-analysis.md"
RANKING_METRICS = (
    "view_count", "bounce_rate_2s", "completion_rate_5s", "completion_rate",
    "favorite_rate", "share_rate", "subscribe_rate",
)
METRIC_FIELDS = RANKING_METRICS + (
    "avg_view_second", "avg_view_proportion", "like_count", "like_rate",
    "comment_count", "comment_rate", "favorite_count", "share_count",
    "subscribe_count", "cover_click_rate", "cover_show", "fan_view_proportion",
)


def _metrics(detail: dict) -> dict:
    values = {}
    for name in METRIC_FIELDS:
        value = detail.get(name)
        if value is None or value == "":
            continue
        try:
            number = float(value)
        except (ValueError, TypeError):
            continue
        if isfinite(number):
            values[name] = int(number) if name.endswith("_count") or name == "cover_show" else number
    return values


def _title_key(title: str) -> str:
    return "".join(title.split())


def _public_work_identity(work: dict) -> tuple[str, datetime]:
    timestamp = (work.get("timer") or {}).get("public_time") or work["create_time"]
    return work.get("item_title") or work.get("desc") or "", datetime.fromtimestamp(timestamp, BEIJING_TIMEZONE)


def _sample_scripts(candidates: list[dict], metric: str, limit: int) -> list[dict]:
    ranked = sorted(candidates, key=lambda row: (row["metrics"][metric], row["work_id"]),
                    reverse=metric != "bounce_rate_2s")
    size = min(len(ranked), limit)
    high_size, remainder = divmod(size, 3)
    low_size = high_size + int(remainder > 1)
    middle_size = high_size
    high_size += int(remainder > 0)
    middle_start = high_size + (len(ranked) - size) // 2
    groups = (
        ("high", ranked[:high_size]),
        ("middle", ranked[middle_start:middle_start + middle_size]),
        ("low", ranked[len(ranked) - low_size:]),
    )
    return [{"work_id": row["work_id"], "cohort": cohort, **row["script"]}
            for cohort, rows in groups for row in rows]


def gather_douyin_performance(days: int, sample_size: int, rank_by: str, minimum_age_hours: int,
                              progress=None) -> dict:
    """返回账号指标、定稿样本、匹配覆盖和宿主分析提示词。"""
    if progress:
        progress("正在用发布器读取财经抖音公开作品及详情")
    snapshot = read_creator_works("finance", metrics_only=True)
    observed_at = datetime.now(BEIJING_TIMEZONE)
    start_at = observed_at - timedelta(days=days)
    cutoff = observed_at - timedelta(hours=minimum_age_hours)
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
        if not start_at <= published_at <= observed_at:
            continue
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
            "metrics": _metrics(details.get(work_id, {})),
            "eligible_age": published_at <= cutoff,
            "match_status": match_status,
            "publication_match": match_type if work_id in publications else None,
        })

    run_ids = sorted({record["run_id"] for record in publications.values()})
    editorials = defaultdict(list)
    for start in range(0, len(run_ids), 100):
        for draft in list_used_editorial_drafts(run_ids[start:start + 100]):
            editorials[(draft["run_id"], _title_key(draft["editorial"]["title"]))].append(draft)

    script_candidates = []
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
        row["source_aweme_id"] = draft["aweme_id"]
        if row["eligible_age"] and rank_by in row["metrics"]:
            editorial = draft["editorial"]
            script_candidates.append({
                **row,
                "script": {
                    "source_aweme_id": draft["aweme_id"],
                    "run_id": record["run_id"],
                    "content_part": record["content_part"],
                    "topic": editorial["topic"],
                    "hook": editorial["source_hook"],
                    "article": editorial["article"],
                },
            })

    return {
        "account_group": "finance",
        "observed_at": observed_at.isoformat(),
        "window_start": start_at.isoformat(),
        "minimum_age_hours": minimum_age_hours,
        "rank_by": rank_by,
        "public_works_in_window": len(works),
        "matched_scripts": sum(row["match_status"] == "matched" for row in works),
        "eligible_scripts": len(script_candidates),
        "works": works,
        "script_sample": _sample_scripts(script_candidates, rank_by, sample_size),
        "analysis_prompt": read_prompt(ANALYSIS_PROMPT_PATH),
    }
