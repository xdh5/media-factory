"""搜索、转写、审核并确认保存抖音研究内容。"""

from __future__ import annotations

import json
import subprocess
from datetime import datetime, timezone
from pathlib import Path

from core.tools.cloudflare_data import (
    CloudflareDataError,
    commit_douyin_research,
    list_douyin_research_ids,
)
from core.tools.transcribe import TranscriptionError, transcribe

from ._constants import (
    BRIDGE_INPUT_FILE_NAME,
    BRIDGE_OUTPUT_FILE_NAME,
    BRIDGE_PATH,
    CONTEXT_FILE_NAME,
    CRAWLER_TIMEOUT_SECONDS,
    DEFAULT_LIMIT,
    MEDIACRAWLER_PYTHON,
    MEDIACRAWLER_ROOT,
    SEARCH_POOL_SIZE,
)
from ._errors import (
    ConfigurationError,
    ConfirmationRequiredError,
    ContextError,
    SearchError,
)

__all__ = ["search_candidates", "review_transcripts", "commit_candidates"]


def _write_json(path: Path, payload: dict) -> None:
    path.parent.mkdir(parents=True, exist_ok=True)
    path.write_text(json.dumps(payload, ensure_ascii=False, indent=2), encoding="utf-8")


def _load_context(context_path: str | Path) -> tuple[Path, dict]:
    path = Path(context_path).resolve()
    if not path.is_file():
        raise ContextError(f"候选上下文不存在：{path}")
    try:
        payload = json.loads(path.read_text(encoding="utf-8"))
    except (OSError, json.JSONDecodeError) as exc:
        raise ContextError(f"候选上下文无法读取：{path}") from exc
    if not isinstance(payload, dict) or not isinstance(payload.get("candidates"), list):
        raise ContextError("候选上下文缺少 candidates 数组")
    return path, payload


def search_candidates(keyword: str, cache_dir: str | Path, *, limit: int = DEFAULT_LIMIT) -> dict:
    """通过 MediaCrawler 搜索并下载新作品，再用项目转写工具识别语音。"""
    clean_keyword = str(keyword or "").strip()
    if not clean_keyword:
        raise SearchError("搜索关键词不能为空")
    if not 1 <= int(limit) <= DEFAULT_LIMIT:
        raise SearchError("候选数量必须为 1 到 5")
    if not MEDIACRAWLER_ROOT.is_dir():
        raise ConfigurationError(f"MediaCrawler 尚未安装：{MEDIACRAWLER_ROOT}")
    if not MEDIACRAWLER_PYTHON.is_file():
        raise ConfigurationError(
            "MediaCrawler 独立依赖尚未安装",
            {"fix": f"请在 {MEDIACRAWLER_ROOT} 执行 uv sync"},
        )
    root = Path(cache_dir).resolve()
    root.mkdir(parents=True, exist_ok=True)
    bridge_input = root / BRIDGE_INPUT_FILE_NAME
    bridge_output = root / BRIDGE_OUTPUT_FILE_NAME
    try:
        excluded_aweme_ids = list_douyin_research_ids()
    except CloudflareDataError as exc:
        raise SearchError(
            f"读取 Cloudflare D1 抖音去重库失败：{exc}",
            getattr(exc, "details", {}),
        ) from exc
    _write_json(bridge_input, {
        "integration_root": str(MEDIACRAWLER_ROOT),
        "keyword": clean_keyword,
        "limit": int(limit),
        "pool_size": SEARCH_POOL_SIZE,
        "excluded_aweme_ids": excluded_aweme_ids,
        "media_root": str(root / "media"),
    })
    try:
        completed = subprocess.run(
            [str(MEDIACRAWLER_PYTHON), str(BRIDGE_PATH), "--input", str(bridge_input), "--output", str(bridge_output)],
            cwd=str(MEDIACRAWLER_ROOT),
            check=False,
            capture_output=True,
            text=True,
            encoding="utf-8",
            errors="replace",
            timeout=CRAWLER_TIMEOUT_SECONDS,
        )
    except subprocess.TimeoutExpired as exc:
        raise SearchError("MediaCrawler 搜索超过 30 分钟，已停止等待") from exc
    if completed.returncode != 0 or not bridge_output.is_file():
        detail = (completed.stderr or completed.stdout or "").strip()[-3000:]
        raise SearchError(f"MediaCrawler 搜索失败：{detail or '没有生成结果文件'}")
    try:
        crawled = json.loads(bridge_output.read_text(encoding="utf-8"))
    except (OSError, json.JSONDecodeError) as exc:
        raise SearchError("MediaCrawler 搜索结果无法解析") from exc
    rows = crawled.get("candidates") if isinstance(crawled, dict) else None
    if not isinstance(rows, list) or not rows:
        raise SearchError("没有找到未入库且可下载的抖音视频")
    candidates = []
    for number, row in enumerate(rows[: int(limit)], 1):
        try:
            recognized = transcribe(row["video_path"], language="zh", filename=f"抖音候选{number}")
        except TranscriptionError as exc:
            raise SearchError(
                f"第 {number} 条视频转写失败：{exc}",
                {"aweme_id": row.get("aweme_id")},
            ) from exc
        candidates.append({
            **row,
            "number": number,
            "transcript_raw": str(recognized["text"]).strip(),
            "transcript_corrected": "",
        })
    context_path = root / CONTEXT_FILE_NAME
    context = {
        "keyword": clean_keyword,
        "created_at": datetime.now(timezone.utc).isoformat(),
        "status": "awaiting_transcript_review",
        "candidates": candidates,
    }
    _write_json(context_path, context)
    return {
        "context_path": str(context_path),
        "candidate_count": len(candidates),
        "transcripts": [
            {"number": row["number"], "text": row["transcript_raw"]}
            for row in candidates
        ],
    }


def review_transcripts(context_path: str | Path, reviews: list[dict]) -> dict:
    """保存宿主 Agent 完成错别字修正和标点整理后的文本。"""
    path, context = _load_context(context_path)
    by_number = {int(row["number"]): row for row in context["candidates"]}
    provided = set()
    for review in reviews:
        number = int(review.get("number") or 0)
        text = str(review.get("text") or "").strip()
        if number not in by_number or not text:
            raise ContextError(f"转写审核内容不合法：候选 {number}")
        by_number[number]["transcript_corrected"] = text
        provided.add(number)
    expected = set(by_number)
    if provided != expected:
        raise ContextError(f"必须一次审核全部候选；缺少编号：{sorted(expected - provided)}")
    context["status"] = "awaiting_user_confirmation"
    _write_json(path, context)
    return {
        "context_path": str(path),
        "transcripts": [
            {"number": number, "text": by_number[number]["transcript_corrected"]}
            for number in sorted(by_number)
        ],
    }


def commit_candidates(
    context_path: str | Path,
    candidate_numbers: list[int],
    *,
    confirmed: bool,
) -> dict:
    """用户确认后，把作品元数据和最终转写幂等写入 D1。"""
    if confirmed is not True:
        raise ConfirmationRequiredError("必须获得用户明确确认后才能把抖音研究内容写入数据库")
    path, context = _load_context(context_path)
    if context.get("status") not in {"awaiting_user_confirmation", "committed"}:
        raise ContextError("全部转写尚未经过宿主 Agent 审核，禁止入库")
    requested = {int(value) for value in candidate_numbers}
    selected = [row for row in context["candidates"] if int(row["number"]) in requested]
    if len(selected) != len(requested) or not selected:
        raise ContextError("确认编号不存在或为空")
    records = []
    for row in selected:
        corrected = str(row.get("transcript_corrected") or "").strip()
        if not corrected:
            raise ContextError(f"候选 {row['number']} 缺少修正后的转写")
        unix_time = int(row.get("published_at_unix") or 0)
        published_at = datetime.fromtimestamp(unix_time, tz=timezone.utc).isoformat() if unix_time else ""
        records.append({
            "aweme_id": str(row["aweme_id"]),
            "source_keyword": str(context["keyword"]),
            "search_rank": int(row["search_rank"]),
            "author_name": str(row.get("author_name") or ""),
            "published_at": published_at,
            "caption": str(row.get("caption") or ""),
            "transcript_raw": str(row.get("transcript_raw") or ""),
            "transcript_corrected": corrected,
            "aweme_url": str(row.get("aweme_url") or ""),
            "cover_url": str(row.get("cover_url") or ""),
        })
    try:
        result = commit_douyin_research(records)
    except CloudflareDataError as exc:
        raise ContextError(
            f"写入 Cloudflare D1 抖音研究库失败：{exc}",
            getattr(exc, "details", {}),
        ) from exc
    context["status"] = "committed"
    context["committed_numbers"] = sorted(requested)
    _write_json(path, context)
    return {
        "context_path": str(path),
        "committed_numbers": sorted(requested),
        "database": result,
    }
