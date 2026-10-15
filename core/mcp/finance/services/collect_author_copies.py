"""按作者配额准备原始转写，交由宿主 Agent 校对及广告审核。"""

from pathlib import Path

from core.tools.transcribe import transcribe
from download_video import download
from list_author_works import list_author_works

from ..errors import WorkflowStepError
from ..infrastructure.source_scripts import list_source_authors, list_saved_script_ids, list_rejected_ad_video_ids
from .copy_review import save_review_context, load_review_context, review_result


def collect_author_copies(count: int, cache_dir: str | Path) -> dict:
    """按作者平分待审数量，未审核前不入库。"""
    if isinstance(count, bool) or not isinstance(count, int) or not 1 <= count <= 300:
        raise WorkflowStepError("抓取数量必须是 1 到 300 的整数")
    authors = list_source_authors()
    if not authors:
        raise WorkflowStepError("财经作者名单为空")
    root = Path(cache_dir).resolve()
    root.mkdir(parents=True, exist_ok=True)
    context = {"requested_count": count, "saved_count": 0, "skipped_ad_count": 0,
               "authors": [], "pending": [], "failures": []}
    base, extra = divmod(count, len(authors))
    for index, author in enumerate(authors):
        quota = base + (1 if index < extra else 0)
        works = []
        if quota:
            try:
                works = list_author_works(author["profile_url"], min(1000, quota * 20))
                works.sort(key=lambda w: w["published_at"], reverse=True)
            except Exception as error:
                context["failures"].append({"author": author["display_name"], "message": str(error)})
        context["authors"].append({**author, "requested_count": quota, "saved_count": 0,
                                   "next_index": 0, "works": works})
    path = root / "copy-review.json"
    save_review_context(path, context)
    return continue_collect_author_copies(str(path))


def continue_collect_author_copies(context_path: str) -> dict:
    """沿用候选列表补足被广告或失败作品占用的配额，不重复启动原任务。"""
    path, context = load_review_context(context_path)
    if context["pending"]:
        return review_result(path, context)
    excluded = set(list_saved_script_ids()) | set(list_rejected_ad_video_ids())
    for author in context["authors"]:
        pending_count = 0
        while author["saved_count"] + pending_count < author["requested_count"]:
            if author["next_index"] >= len(author["works"]):
                break
            work = author["works"][author["next_index"]]
            author["next_index"] += 1
            save_review_context(path, context)
            if work["aweme_id"] in excluded or not work["is_video"]:
                continue
            try:
                downloaded = download(work["work_url"], path.parent / work["aweme_id"] / "video.mp4")
                recognized = transcribe(downloaded["video_path"], language="zh", filename=f"抖音作品{work['aweme_id']}")
                original = str(recognized.get("raw_text") or "").strip()
                if not original:
                    raise WorkflowStepError("作品转写为空")
            except Exception as error:
                context["failures"].append({"aweme_id": work["aweme_id"], "message": str(error)})
                save_review_context(path, context)
                continue
            context["pending"].append({
                "aweme_id": work["aweme_id"], "sec_user_id": author["sec_user_id"],
                "collection_code": "finance", "collection_name": "财经",
                "search_keyword": "author_homepage", "search_rank": author["saved_count"] + pending_count + 1,
                "author_name": work["author_name"] or author["display_name"],
                "published_at": work["published_at"], "caption": work["title"] or "无文案",
                "transcript_raw": original, "aweme_url": work["work_url"], "cover_url": work["cover_url"],
            })
            pending_count += 1
            excluded.add(work["aweme_id"])
            save_review_context(path, context)
            print(f"原始转写已准备：{author['display_name']}，{work['aweme_id']}", flush=True)
    return review_result(path, context)
