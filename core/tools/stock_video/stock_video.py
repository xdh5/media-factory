"""通过 Pexels、Pixabay、Coverr 搜索、下载并规范化正版视频素材。"""

from __future__ import annotations

import json
import hashlib
import os
import shutil
import subprocess
import time
from pathlib import Path
from urllib.error import HTTPError, URLError
from urllib.parse import urlencode, urlparse
from urllib.request import Request, urlopen

from dotenv import load_dotenv

from ._constants import (
    ALLOWED_DOWNLOAD_HOST_SUFFIXES,
    ATTRIBUTION_URLS,
    COVERR_API_KEY_ENV,
    COVERR_API_URL,
    DEFAULT_RESULTS_PER_PROVIDER,
    DEFAULT_TIMEOUT_SECONDS,
    MAX_DOWNLOAD_BYTES,
    MAX_RESULTS_PER_PROVIDER,
    PEXELS_API_KEY_ENV,
    PEXELS_API_URL,
    PIXABAY_API_KEY_ENV,
    PIXABAY_API_URL,
    PROVIDER_PRIORITY,
    SEARCH_CACHE_SECONDS,
)
from ._errors import (
    StockVideoConfigurationError,
    StockVideoDownloadError,
    StockVideoRenderError,
    StockVideoRequestError,
)


def _project_root() -> Path:
    for candidate in Path(__file__).resolve().parents:
        if any((candidate / name).is_file() for name in ("AGENTS.md", "agents.md")):
            return candidate
    raise StockVideoConfigurationError("找不到项目根目录：缺少 AGENTS.md 或 agents.md")


def _search_cache_path(provider: str, query: str, orientation: str, limit: int) -> Path:
    signature = hashlib.sha256(
        json.dumps([provider, query, orientation, limit], ensure_ascii=False).encode("utf-8")
    ).hexdigest()
    return _project_root() / "cache" / "stock_video" / "search" / f"{signature}.json"


def _read_search_cache(path: Path) -> list[dict] | None:
    if not path.is_file() or time.time() - path.stat().st_mtime > SEARCH_CACHE_SECONDS:
        return None
    try:
        payload = json.loads(path.read_text(encoding="utf-8"))
    except (OSError, json.JSONDecodeError):
        return None
    return payload if isinstance(payload, list) else None


def _write_search_cache(path: Path, candidates: list[dict]) -> None:
    path.parent.mkdir(parents=True, exist_ok=True)
    path.write_text(json.dumps(candidates, ensure_ascii=False, indent=2), encoding="utf-8")

load_dotenv()


def _request_json(url: str, *, headers: dict[str, str] | None = None) -> dict:
    request = Request(url, headers={"User-Agent": "media-factory/1.0", **(headers or {})})
    try:
        with urlopen(request, timeout=DEFAULT_TIMEOUT_SECONDS) as response:
            raw = response.read(8 * 1024 * 1024 + 1)
    except HTTPError as exc:
        detail = exc.read(2048).decode("utf-8", errors="replace")
        exc.close()
        raise StockVideoRequestError(
            f"视频素材接口请求失败（HTTP {exc.code}）：{detail[:300]}",
            {"url": url, "status": exc.code},
        ) from exc
    except (URLError, TimeoutError, OSError) as exc:
        raise StockVideoRequestError(f"连接视频素材接口失败：{exc}", {"url": url}) from exc
    if len(raw) > 8 * 1024 * 1024:
        raise StockVideoRequestError("视频素材接口响应超过8MB", {"url": url})
    try:
        payload = json.loads(raw.decode("utf-8"))
    except (UnicodeDecodeError, json.JSONDecodeError) as exc:
        raise StockVideoRequestError("视频素材接口返回的不是有效 JSON", {"url": url}) from exc
    if not isinstance(payload, dict):
        raise StockVideoRequestError("视频素材接口必须返回 JSON 对象", {"url": url})
    return payload


def _best_variant(variants: list[dict], orientation: str) -> dict | None:
    valid = [
        row for row in variants
        if str(row.get("url") or row.get("link") or "").startswith("https://")
        and int(row.get("width") or 0) > 0
        and int(row.get("height") or 0) > 0
    ]
    if not valid:
        return None
    # 成片统一规范化到 1920x1080，选最接近 Full HD 的版本即可，
    # 避免为 4K 原片付出 10 倍下载体积（2026-09-23：163MB 原片拖垮整条生产线）。
    target_pixels = 1920 * 1080

    def score(row: dict) -> tuple[int, int]:
        width, height = int(row.get("width") or 0), int(row.get("height") or 0)
        matches = (
            (orientation == "landscape" and width >= height)
            or (orientation == "portrait" and height > width)
            or (orientation == "square" and abs(width - height) <= max(width, height) * 0.15)
        )
        return (1 if matches else 0, -abs(width * height - target_pixels))
    return max(valid, key=score)


def _search_pexels(query: str, orientation: str, limit: int, api_key: str) -> list[dict]:
    payload = _request_json(
        PEXELS_API_URL + "?" + urlencode({
            "query": query,
            "orientation": orientation,
            "size": "medium",
            "locale": "en-US",
            "per_page": limit,
        }),
        headers={"Authorization": api_key},
    )
    results = []
    for row in payload.get("videos") or []:
        variant = _best_variant([
            {**item, "url": item.get("link")} for item in row.get("video_files") or []
            if str(item.get("file_type") or "") == "video/mp4"
        ], orientation)
        if not variant:
            continue
        user = row.get("user") if isinstance(row.get("user"), dict) else {}
        creator = str(user.get("name") or "Pexels 创作者")
        results.append({
            "provider": "pexels",
            "id": str(row.get("id") or ""),
            "title": str(row.get("url") or "").rstrip("/").rsplit("/", 1)[-1].replace("-", " "),
            "page_url": str(row.get("url") or ATTRIBUTION_URLS["pexels"]),
            "download_url": str(variant.get("url") or ""),
            "preview_url": str(row.get("image") or ""),
            "duration": float(row.get("duration") or 0),
            "width": int(variant.get("width") or 0),
            "height": int(variant.get("height") or 0),
            "creator": creator,
            "attribution": f"Video by {creator} on Pexels",
            "attribution_url": ATTRIBUTION_URLS["pexels"],
        })
    return results


def _search_pixabay(query: str, orientation: str, limit: int, api_key: str) -> list[dict]:
    payload = _request_json(PIXABAY_API_URL + "?" + urlencode({
        "key": api_key,
        "q": query,
        "lang": "en",
        "video_type": "film",
        "safesearch": "true",
        "order": "popular",
        "per_page": max(3, limit),
    }))
    results = []
    for row in payload.get("hits") or []:
        variants = []
        for item in (row.get("videos") or {}).values():
            if isinstance(item, dict):
                variants.append(item)
        variant = _best_variant(variants, orientation)
        if not variant:
            continue
        creator = str(row.get("user") or "Pixabay 创作者")
        results.append({
            "provider": "pixabay",
            "id": str(row.get("id") or ""),
            "title": str(row.get("tags") or "Pixabay video"),
            "page_url": str(row.get("pageURL") or ATTRIBUTION_URLS["pixabay"]),
            "download_url": str(variant.get("url") or ""),
            "preview_url": str(variant.get("thumbnail") or ""),
            "duration": float(row.get("duration") or 0),
            "width": int(variant.get("width") or 0),
            "height": int(variant.get("height") or 0),
            "creator": creator,
            "attribution": f"Video by {creator} on Pixabay",
            "attribution_url": ATTRIBUTION_URLS["pixabay"],
        })
    return results[:limit]


def _search_coverr(query: str, orientation: str, limit: int, api_key: str) -> list[dict]:
    payload = _request_json(
        COVERR_API_URL + "?" + urlencode({
            "query": query,
            "page": 0,
            "page_size": limit,
            "sort": "popular",
            "urls": "true",
        }),
        headers={"Authorization": f"Bearer {api_key}"},
    )
    results = []
    for row in payload.get("hits") or []:
        is_vertical = bool(row.get("is_vertical"))
        if orientation == "landscape" and is_vertical:
            continue
        if orientation == "portrait" and not is_vertical:
            continue
        urls = row.get("urls") if isinstance(row.get("urls"), dict) else {}
        download_url = str(urls.get("mp4_download") or urls.get("mp4") or "")
        if not download_url.startswith("https://"):
            continue
        creator_data = row.get("user") if isinstance(row.get("user"), dict) else {}
        creator = str(creator_data.get("name") or row.get("creator") or "Coverr 创作者")
        results.append({
            "provider": "coverr",
            "id": str(row.get("id") or row.get("slug") or ""),
            "title": str(row.get("title") or row.get("description") or "Coverr video"),
            "page_url": str(row.get("url") or ATTRIBUTION_URLS["coverr"]),
            "download_url": download_url,
            "preview_url": str(row.get("thumbnail") or row.get("poster") or ""),
            "duration": float(row.get("duration") or 0),
            "width": int(row.get("max_width") or (1080 if is_vertical else 1920)),
            "height": int(row.get("max_height") or (1920 if is_vertical else 1080)),
            "creator": creator,
            "attribution": f"Video by {creator} on Coverr",
            "attribution_url": ATTRIBUTION_URLS["coverr"],
        })
    return results


def search_stock_videos(
    query: str,
    *,
    orientation: str = "landscape",
    per_provider: int = DEFAULT_RESULTS_PER_PROVIDER,
    providers: list[str] | tuple[str, ...] | None = None,
) -> dict:
    """按 Pexels → Pixabay → Coverr 顺序搜索，上一站无结果或失败才使用下一站。"""
    normalized_query = str(query or "").strip()
    if not normalized_query or len(normalized_query) > 100:
        raise StockVideoConfigurationError("query 必须为1～100个字符")
    if orientation not in {"landscape", "portrait", "square"}:
        raise StockVideoConfigurationError("orientation 必须是 landscape、portrait 或 square")
    limit = int(per_provider)
    if not 1 <= limit <= MAX_RESULTS_PER_PROVIDER:
        raise StockVideoConfigurationError(f"per_provider 必须为1～{MAX_RESULTS_PER_PROVIDER}")
    ordered = tuple(providers or PROVIDER_PRIORITY)
    if not ordered or any(item not in PROVIDER_PRIORITY for item in ordered):
        raise StockVideoConfigurationError(f"providers 只能从 {list(PROVIDER_PRIORITY)} 中选择")
    keys = {
        "pexels": os.getenv(PEXELS_API_KEY_ENV, "").strip(),
        "pixabay": os.getenv(PIXABAY_API_KEY_ENV, "").strip(),
        "coverr": os.getenv(COVERR_API_KEY_ENV, "").strip(),
    }
    attempts = []
    for provider in ordered:
        if not keys[provider]:
            attempts.append({"provider": provider, "status": "skipped", "reason": "缺少 API Key"})
            continue
        try:
            cache_path = _search_cache_path(provider, normalized_query, orientation, limit)
            candidates = _read_search_cache(cache_path)
            cache_hit = candidates is not None
            if candidates is None:
                if provider == "pexels":
                    candidates = _search_pexels(normalized_query, orientation, limit, keys[provider])
                elif provider == "pixabay":
                    candidates = _search_pixabay(normalized_query, orientation, limit, keys[provider])
                else:
                    candidates = _search_coverr(normalized_query, orientation, limit, keys[provider])
                _write_search_cache(cache_path, candidates)
        except StockVideoRequestError as exc:
            attempts.append({"provider": provider, "status": "failed", "reason": exc.message})
            continue
        attempts.append({
            "provider": provider,
            "status": "succeeded",
            "count": len(candidates),
            "cache_hit": cache_hit,
        })
        if candidates:
            return {
                "query": normalized_query,
                "orientation": orientation,
                "provider": provider,
                "candidates": candidates,
                "attempts": attempts,
            }
    raise StockVideoRequestError(
        "三个正版视频站均未返回可用素材，请更换英文关键词或检查 API Key",
        {"query": normalized_query, "attempts": attempts},
    )


def _allowed_download_url(provider: str, url: str) -> bool:
    parsed = urlparse(url)
    host = (parsed.hostname or "").casefold()
    return parsed.scheme == "https" and any(
        host == suffix.lstrip(".") or host.endswith(suffix)
        for suffix in ALLOWED_DOWNLOAD_HOST_SUFFIXES.get(provider, ())
    )


def _curl_download(provider: str, url: str, temporary: Path) -> str:
    """用 curl 下载（urlopen 在代理环境下会出现 socket 超时不生效的假活连接）。

    --speed-limit/--speed-time 组合在"连接假活、几乎无数据"时主动掐断，
    --max-time 给整个下载设总上限；返回 curl 看到的最终跳转 URL。
    """
    command = [
        "curl", "-L", "--fail", "--silent", "--show-error",
        "--connect-timeout", str(DEFAULT_TIMEOUT_SECONDS),
        "--max-time", "600",
        "--speed-limit", "10240", "--speed-time", "30",
        "--user-agent", "media-factory/1.0",
        "--output", str(temporary),
        "--write-out", "%{url_effective}",
        url,
    ]
    result = subprocess.run(command, capture_output=True, text=True, timeout=660)
    if result.returncode != 0:
        raise StockVideoDownloadError(
            f"curl 下载视频素材失败（exit {result.returncode}）：{result.stderr.strip()[:300]}",
            {"provider": provider},
        )
    lines = [line.strip() for line in result.stdout.splitlines() if line.strip()]
    if not lines:
        raise StockVideoDownloadError("curl 未返回最终跳转地址", {"provider": provider})
    return lines[-1]


def download_stock_video(candidate: dict, output_path: str | Path) -> dict:
    """下载已选择的官方 API 候选视频到本地，不接受任意网址。

    目标文件已存在且非空时直接跳过（重跑幂等，不重复下载）。
    """
    provider = str(candidate.get("provider") or "").strip()
    url = str(candidate.get("download_url") or "").strip()
    if provider not in PROVIDER_PRIORITY or not _allowed_download_url(provider, url):
        raise StockVideoDownloadError("候选视频来源或下载域名不受支持", {"provider": provider, "url": url})
    destination = Path(output_path).resolve()
    if destination.suffix.lower() != ".mp4":
        raise StockVideoDownloadError("output_path 必须使用 .mp4 扩展名")
    if destination.is_file() and destination.stat().st_size > 0:
        return {
            "output_path": str(destination),
            "bytes": destination.stat().st_size,
            "candidate": candidate,
            "skipped_existing": True,
        }
    destination.parent.mkdir(parents=True, exist_ok=True)
    temporary = destination.with_suffix(destination.suffix + ".part")
    last_error: StockVideoDownloadError | None = None
    for attempt in range(2):
        try:
            final_url = _curl_download(provider, url, temporary)
            if not _allowed_download_url(provider, final_url):
                raise StockVideoDownloadError(
                    "视频下载跳转到了不受支持的域名",
                    {"provider": provider, "final_url": final_url},
                )
            length = temporary.stat().st_size if temporary.is_file() else 0
            if length <= 0:
                raise StockVideoDownloadError("下载内容为空", {"provider": provider})
            if length > MAX_DOWNLOAD_BYTES:
                raise StockVideoDownloadError("视频素材超过300MB限制", {"content_length": length})
            os.replace(temporary, destination)
            return {
                "output_path": str(destination),
                "bytes": destination.stat().st_size,
                "candidate": candidate,
            }
        except StockVideoDownloadError as exc:
            if temporary.exists():
                temporary.unlink()
            last_error = exc
            if attempt == 0:
                time.sleep(3)
        except (subprocess.TimeoutExpired, OSError) as exc:
            if temporary.exists():
                temporary.unlink()
            last_error = StockVideoDownloadError(
                f"下载视频素材失败：{exc}", {"provider": provider}
            )
            if attempt == 0:
                time.sleep(3)
    raise last_error


def prepare_stock_clip(
    source_path: str | Path,
    output_path: str | Path,
    duration: float,
    *,
    size: str = "1920x1080",
    frame_path: str | Path | None = None,
) -> dict:
    """循环、裁切并静音规范化素材，使镜头时长与配音严格一致。"""
    source = Path(source_path).resolve()
    destination = Path(output_path).resolve()
    if not source.is_file():
        raise StockVideoRenderError(f"源视频不存在：{source}")
    try:
        width_text, height_text = str(size).lower().split("x", 1)
        width, height = int(width_text), int(height_text)
        seconds = float(duration)
    except (TypeError, ValueError) as exc:
        raise StockVideoRenderError("size 必须是宽x高，duration 必须是正数") from exc
    if width < 2 or height < 2 or width % 2 or height % 2 or seconds <= 0:
        raise StockVideoRenderError("输出宽高必须是正偶数，duration 必须大于0")
    ffmpeg = shutil.which("ffmpeg")
    if not ffmpeg:
        raise StockVideoRenderError("找不到 ffmpeg，请先安装或加入 PATH")
    destination.parent.mkdir(parents=True, exist_ok=True)
    filter_value = (
        f"scale={width}:{height}:force_original_aspect_ratio=increase,"
        f"crop={width}:{height},setsar=1,fps=30"
    )
    command = [
        ffmpeg, "-hide_banner", "-loglevel", "error", "-y", "-stream_loop", "-1",
        "-i", str(source), "-t", f"{seconds:.6f}", "-an", "-vf", filter_value,
        "-c:v", "libx264", "-preset", "medium", "-crf", "20", "-pix_fmt", "yuv420p",
        "-movflags", "+faststart", str(destination),
    ]
    result = subprocess.run(command, capture_output=True, text=True, encoding="utf-8", errors="replace")
    if result.returncode != 0 or not destination.is_file():
        raise StockVideoRenderError(
            f"规范化视频素材失败：{result.stderr[-1000:]}",
            {"source_path": str(source), "output_path": str(destination)},
        )
    rendered_frame = None
    if frame_path is not None:
        frame = Path(frame_path).resolve()
        frame.parent.mkdir(parents=True, exist_ok=True)
        frame_result = subprocess.run(
            [ffmpeg, "-hide_banner", "-loglevel", "error", "-y", "-ss", "0.2", "-i", str(destination), "-frames:v", "1", str(frame)],
            capture_output=True,
            text=True,
            encoding="utf-8",
            errors="replace",
        )
        if frame_result.returncode != 0 or not frame.is_file():
            raise StockVideoRenderError(f"提取视频封面帧失败：{frame_result.stderr[-1000:]}")
        rendered_frame = str(frame)
    return {
        "output_path": str(destination),
        "frame_path": rendered_frame,
        "duration": seconds,
        "size": f"{width}x{height}",
    }
