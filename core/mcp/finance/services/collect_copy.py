"""下载抖音链接并转写原文，等待宿主校对和审核。"""

from __future__ import annotations

from pathlib import Path

from .copy_review import save_review_context, review_result
from core.tools.transcribe import TranscriptionError, transcribe
from download_video import DownloadError, download

from ..errors import WorkflowStepError

_PROJECT_ROOT = Path(__file__).resolve().parents[4]
CACHE_ROOT = _PROJECT_ROOT / "cache" / "collect_finance_copy"
_VIDEO_FILE_NAME = "video.mp4"
_DIRECT_LINK_SOURCE = "direct_link"
_COLLECTION_CODE_BY_NAME = {"财经": "finance"}


def collect_copy(
    share_text: str,
    cache_dir: str | Path,
    *,
    collection_name: str,
) -> dict:
    """下载单条抖音链接，返回未入库的待审原文。"""
    clean_share_text = str(share_text or "").strip()
    clean_collection_name = str(collection_name or "").strip()
    if not clean_share_text:
        raise WorkflowStepError("抖音链接不能为空")
    collection_code = _COLLECTION_CODE_BY_NAME.get(clean_collection_name)
    if not collection_code:
        raise WorkflowStepError("分类名称仅支持“财经”，请将 collection_name 设置为“财经”")
    if len(clean_collection_name) > 100:
        raise WorkflowStepError("分类名称必须是 1 到 100 个字符")

    root = Path(cache_dir).resolve()
    root.mkdir(parents=True, exist_ok=True)
    try:
        downloaded = download(clean_share_text, root / _VIDEO_FILE_NAME)
    except DownloadError as exc:
        raise WorkflowStepError(
            f"抖音视频下载失败：{exc}",
            getattr(exc, "details", {}),
        ) from exc

    platform = str(downloaded.get("platform") or "").strip()
    video_id = str(downloaded.get("video_id") or "").strip()
    if platform != "抖音":
        raise WorkflowStepError(f"链接平台必须是抖音，当前识别为：{platform or '未知平台'}")
    if not video_id.isdigit():
        raise WorkflowStepError("下载结果缺少有效的抖音作品 ID")

    try:
        recognized = transcribe(
            downloaded["video_path"],
            language="zh",
            filename=f"抖音作品{video_id}",
        )
    except TranscriptionError as exc:
        raise WorkflowStepError(
            f"抖音视频转写失败：{exc}",
            getattr(exc, "details", {}),
        ) from exc

    transcript = str(recognized.get("text") or "").strip()
    raw_transcript = str(recognized.get("raw_text") or transcript).strip()
    if not transcript:
        raise WorkflowStepError("抖音视频转写结果为空，未写入数据库")

    record = {
        "aweme_id": video_id,
        "collection_code": collection_code,
        "collection_name": clean_collection_name,
        "search_keyword": _DIRECT_LINK_SOURCE,
        "search_rank": 1,
        "author_name": "未知作者",
        "published_at": "",
        "caption": str(downloaded.get("title") or "无文案").strip() or "无文案",
        "transcript_raw": raw_transcript,
        "aweme_url": f"https://www.douyin.com/video/{video_id}",
        "cover_url": str(downloaded.get("cover_url") or "").strip(),
    }
    context = {"requested_count": 1, "saved_count": 0, "skipped_ad_count": 0,
               "pending": [record], "failures": []}
    path = root / "copy-review.json"
    save_review_context(path, context)
    return review_result(path, context)
