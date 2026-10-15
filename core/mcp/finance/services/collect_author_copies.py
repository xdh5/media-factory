"""按作者名单平分抓取最新财经口播，去重后去掉广告再入库。"""

from __future__ import annotations

from pathlib import Path

from core.tools.media_records import MediaRecordsError
from core.tools.transcribe import TranscriptionError, transcribe
from download_video import DownloadError, download
from list_author_works import AuthorWorksError, list_author_works

from ..errors import WorkflowStepError
from ..infrastructure.source_scripts import (
    list_rejected_ad_video_ids,
    list_saved_script_ids,
    list_source_authors,
    remember_rejected_ad_video,
    save_transcribed_scripts,
)
from .collect_copy import CACHE_ROOT
from .copy_ad_review import review_finance_transcript

_COLLECTION_NAME = "财经"
_COLLECTION_CODE = "finance"
_SOURCE_KEYWORD = "author_homepage"
_MAX_COUNT = 300
_SCAN_FACTOR = 20
_COMMIT_BATCH = 5


def _quotas(count: int, author_count: int) -> list[int]:
    base, extra = divmod(count, author_count)
    return [base + (1 if index < extra else 0) for index in range(author_count)]


def _failure(author: dict, message: str, aweme_id: str = "") -> dict:
    return {
        "sec_user_id": author["sec_user_id"],
        "display_name": author.get("display_name") or "",
        "aweme_id": aweme_id,
        "message": message,
    }


def _commit(records: list[dict], databases: list[dict]) -> None:
    if not records:
        return
    try:
        databases.append(save_transcribed_scripts(records))
    except MediaRecordsError as extra:
        raise WorkflowStepError(
            f"写入财经文案库失败：{extra}",
            getattr(extra, "details", {}),
        ) from extra
    records.clear()


def collect_author_copies(count: int, cache_dir: str | Path) -> dict:
    """按当前作者人数平分 count，每人从最新作品里取够未入库的正常口播。"""
    if isinstance(count, bool) or not isinstance(count, int) or not 1 <= count <= _MAX_COUNT:
        raise WorkflowStepError(f"抓取数量必须是 1 到 {_MAX_COUNT} 的整数")
    try:
        authors = list_source_authors()
    except MediaRecordsError as extra:
        raise WorkflowStepError(
            f"读取财经作者名单失败：{extra}",
            getattr(extra, "details", {}),
        ) from extra
    if not authors:
        raise WorkflowStepError("财经作者名单是空的，请先添加作者主页")

    try:
        stored_ids = set(list_saved_script_ids())
        rejected_ids = set(list_rejected_ad_video_ids())
    except MediaRecordsError as extra:
        raise WorkflowStepError(
            f"读取已入库作品失败：{extra}",
            getattr(extra, "details", {}),
        ) from extra

    root = Path(cache_dir).resolve()
    root.mkdir(parents=True, exist_ok=True)
    quotas = _quotas(count, len(authors))
    pending: list[dict] = []
    databases: list[dict] = []
    author_results: list[dict] = []
    failures: list[dict] = []
    skipped_duplicate = 0
    skipped_ad = 0
    skipped_not_video = 0
    saved_count = 0

    for author, quota in zip(authors, quotas):
        saved_for_author = 0
        if quota <= 0:
            author_results.append({
                "sec_user_id": author["sec_user_id"],
                "display_name": author.get("display_name") or "",
                "requested_count": 0,
                "saved_count": 0,
            })
            continue
        scan_limit = min(1000, max(quota * _SCAN_FACTOR, quota))
        try:
            works = list_author_works(author["profile_url"], scan_limit)
        except AuthorWorksError as extra:
            failures.append(_failure(author, extra.message))
            author_results.append({
                "sec_user_id": author["sec_user_id"],
                "display_name": author.get("display_name") or "",
                "requested_count": quota,
                "saved_count": 0,
            })
            continue

        examined = 0
        for work in works:
            if saved_for_author >= quota:
                break
            examined += 1
            aweme_id = work["aweme_id"]
            if aweme_id in stored_ids:
                skipped_duplicate += 1
                continue
            if aweme_id in rejected_ids:
                skipped_ad += 1
                continue
            if not work["is_video"]:
                skipped_not_video += 1
                continue
            video_path = root / aweme_id / "video.mp4"
            try:
                downloaded = download(work["work_url"], video_path)
                recognized = transcribe(
                    downloaded["video_path"],
                    language="zh",
                    filename=f"抖音作品{aweme_id}",
                )
                transcript = str(recognized.get("text") or "").strip()
                raw_transcript = str(recognized.get("raw_text") or transcript).strip()
                if not transcript:
                    raise WorkflowStepError("转写结果为空")
                reviewed = review_finance_transcript(transcript)
            except (DownloadError, TranscriptionError, WorkflowStepError) as extra:
                failures.append(_failure(author, str(getattr(extra, "message", extra)), aweme_id))
                continue
            if reviewed["kind"] == "ad":
                skipped_ad += 1
                rejected_ids.add(aweme_id)
                try:
                    remember_rejected_ad_video(aweme_id)
                except MediaRecordsError as extra:
                    failures.append(_failure(author, f"记录广告作品失败：{extra}", aweme_id))
                continue
            saved_for_author += 1
            saved_count += 1
            stored_ids.add(aweme_id)
            author_name = work["author_name"] or author.get("display_name") or "未知作者"
            pending.append({
                "aweme_id": aweme_id,
                "collection_code": _COLLECTION_CODE,
                "collection_name": _COLLECTION_NAME,
                "search_keyword": _SOURCE_KEYWORD,
                "search_rank": saved_for_author,
                "author_name": author_name,
                "published_at": work["published_at"],
                "caption": work["title"] or "无文案",
                "transcript_raw": raw_transcript,
                "transcript_corrected": reviewed["text"],
                "aweme_url": work["work_url"],
                "cover_url": work["cover_url"],
            })
            if len(pending) >= _COMMIT_BATCH:
                _commit(pending, databases)
        author_results.append({
            "sec_user_id": author["sec_user_id"],
            "display_name": author.get("display_name") or "",
            "requested_count": quota,
            "saved_count": saved_for_author,
            "examined_count": examined,
        })

    _commit(pending, databases)
    if saved_count == 0 and failures and skipped_ad == 0 and skipped_duplicate == 0:
        raise WorkflowStepError(
            f"没有抓到可入库的财经稿件：{failures[0]['message']}",
            {"failures": failures[:10]},
        )
    return {
        "requested_count": count,
        "author_count": len(authors),
        "saved_count": saved_count,
        "skipped_duplicate_count": skipped_duplicate,
        "skipped_ad_count": skipped_ad,
        "skipped_not_video_count": skipped_not_video,
        "authors": author_results,
        "failures": failures[:20],
        "database": databases,
    }
