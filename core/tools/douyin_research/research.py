"""下载抖音链接、转写并分类写入数据库。"""

from __future__ import annotations

import hashlib
from pathlib import Path

from core.tools.cloudflare_data import CloudflareDataError, commit_douyin_research
from core.tools.download import DownloadError, download
from core.tools.transcribe import TranscriptionError, transcribe

from ._constants import COLLECTION_CODE_BY_NAME, DIRECT_LINK_SOURCE, VIDEO_FILE_NAME
from ._errors import IngestError

__all__ = ["ingest_link"]


def _collection_code(collection_name: str) -> str:
    known = COLLECTION_CODE_BY_NAME.get(collection_name)
    if known:
        return known
    digest = hashlib.sha256(collection_name.encode("utf-8")).hexdigest()[:12]
    return f"category-{digest}"


def ingest_link(
    share_text: str,
    cache_dir: str | Path,
    *,
    collection_name: str,
) -> dict:
    """下载单条抖音链接，转写后直接分类写入 D1。"""
    clean_share_text = str(share_text or "").strip()
    clean_collection_name = str(collection_name or "").strip()
    if not clean_share_text:
        raise IngestError("抖音链接不能为空")
    if not clean_collection_name or len(clean_collection_name) > 100:
        raise IngestError("分类名称必须是 1 到 100 个字符")

    root = Path(cache_dir).resolve()
    root.mkdir(parents=True, exist_ok=True)
    try:
        downloaded = download(clean_share_text, root / VIDEO_FILE_NAME)
    except DownloadError as exc:
        raise IngestError(
            f"抖音视频下载失败：{exc}",
            getattr(exc, "details", {}),
        ) from exc

    platform = str(downloaded.get("platform") or "").strip()
    video_id = str(downloaded.get("video_id") or "").strip()
    if platform != "抖音":
        raise IngestError(f"链接平台必须是抖音，当前识别为：{platform or '未知平台'}")
    if not video_id.isdigit():
        raise IngestError("下载结果缺少有效的抖音作品 ID")

    try:
        recognized = transcribe(
            downloaded["video_path"],
            language="zh",
            filename=f"抖音作品{video_id}",
        )
    except TranscriptionError as exc:
        raise IngestError(
            f"抖音视频转写失败：{exc}",
            getattr(exc, "details", {}),
        ) from exc

    transcript = str(recognized.get("text") or "").strip()
    if not transcript:
        raise IngestError("抖音视频转写结果为空，未写入数据库")

    collection_code = _collection_code(clean_collection_name)
    record = {
        "aweme_id": video_id,
        "collection_code": collection_code,
        "collection_name": clean_collection_name,
        "search_keyword": DIRECT_LINK_SOURCE,
        "search_rank": 1,
        "author_name": "未知作者",
        "published_at": "",
        "caption": str(downloaded.get("title") or "无文案").strip() or "无文案",
        "transcript_raw": transcript,
        "transcript_corrected": transcript,
        "aweme_url": f"https://www.douyin.com/video/{video_id}",
        "cover_url": str(downloaded.get("cover_url") or "").strip(),
    }
    try:
        database = commit_douyin_research([record])
    except CloudflareDataError as exc:
        raise IngestError(
            f"写入 Cloudflare D1 抖音研究库失败：{exc}",
            getattr(exc, "details", {}),
        ) from exc

    return {
        "aweme_id": video_id,
        "collection_code": collection_code,
        "collection_name": clean_collection_name,
        "transcript": transcript,
        "video_path": str(downloaded["video_path"]),
        "database": database,
    }
