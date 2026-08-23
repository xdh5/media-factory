"""在 MediaCrawler 独立环境中搜索并下载抖音候选视频。"""

from __future__ import annotations

import argparse
import asyncio
import json
import os
import sys
from pathlib import Path
from types import MethodType


def _arguments() -> argparse.Namespace:
    parser = argparse.ArgumentParser()
    parser.add_argument("--input", required=True)
    parser.add_argument("--output", required=True)
    return parser.parse_args()


def _candidate(item: dict, *, rank: int, video_path: Path) -> dict:
    author = item.get("author") if isinstance(item.get("author"), dict) else {}
    statistics = item.get("statistics") if isinstance(item.get("statistics"), dict) else {}
    video = item.get("video") if isinstance(item.get("video"), dict) else {}
    cover = video.get("raw_cover") or video.get("origin_cover") or {}
    cover_urls = cover.get("url_list") if isinstance(cover, dict) else []
    return {
        "aweme_id": str(item.get("aweme_id") or ""),
        "search_rank": rank,
        "author_name": str(author.get("nickname") or ""),
        "published_at_unix": int(item.get("create_time") or 0),
        "caption": str(item.get("desc") or ""),
        "aweme_url": f"https://www.douyin.com/video/{item.get('aweme_id') or ''}",
        "cover_url": str(cover_urls[-1]) if cover_urls else "",
        "liked_count": int(statistics.get("digg_count") or 0),
        "comment_count": int(statistics.get("comment_count") or 0),
        "share_count": int(statistics.get("share_count") or 0),
        "video_path": str(video_path.resolve()),
        "download_source": "MediaCrawler",
    }


async def _run(payload: dict) -> dict:
    integration_root = Path(str(payload["integration_root"])).resolve()
    sys.path.insert(0, str(integration_root))
    os.chdir(integration_root)

    import config
    from media_platform.douyin.core import DouYinCrawler
    from var import source_keyword_var

    keyword = str(payload["keyword"]).strip()
    limit = int(payload["limit"])
    pool_size = int(payload["pool_size"])
    excluded = {str(value) for value in payload.get("excluded_aweme_ids") or []}
    output_root = Path(str(payload["media_root"])).resolve()
    output_root.mkdir(parents=True, exist_ok=True)

    config.PLATFORM = "dy"
    config.CRAWLER_TYPE = "search"
    config.KEYWORDS = keyword
    config.ENABLE_GET_COMMENTS = False
    config.ENABLE_GET_SUB_COMMENTS = False
    config.ENABLE_GET_MEIDAS = True
    config.MAX_CONCURRENCY_NUM = 1
    config.CRAWLER_MAX_SLEEP_SEC = 2
    config.SAVE_DATA_PATH = str(output_root)
    config.ENABLE_CDP_MODE = True
    config.CDP_CONNECT_EXISTING = os.getenv(
        "DOUYIN_CRAWLER_CONNECT_EXISTING", "false"
    ).strip().lower() in {"1", "true", "yes"}
    config.AUTO_CLOSE_BROWSER = True
    config.HEADLESS = os.getenv("DOUYIN_CRAWLER_HEADLESS", "false").strip().lower() in {"1", "true", "yes"}
    config.CDP_HEADLESS = config.HEADLESS
    cookie = os.getenv("DOUYIN_COOKIE", "").strip()
    config.COOKIES = cookie
    config.LOGIN_TYPE = "cookie" if cookie else "qrcode"

    captured: list[dict] = []
    original_get_media = DouYinCrawler.get_aweme_media

    async def search_selected(self) -> None:
        source_keyword_var.set(keyword)
        page = 1
        search_id = ""
        seen: set[str] = set()
        inspected = 0
        while len(captured) < limit and inspected < pool_size:
            response = await self.dy_client.search_info_by_keyword(
                keyword=keyword,
                offset=(page - 1) * 10,
                search_id=search_id,
            )
            rows = response.get("data") or []
            if not rows:
                break
            search_id = str((response.get("extra") or {}).get("logid") or "")
            for row in rows:
                item = row.get("aweme_info")
                if not item:
                    mix = row.get("aweme_mix_info") or {}
                    items = mix.get("mix_items") or []
                    item = items[0] if items else None
                if not isinstance(item, dict):
                    continue
                aweme_id = str(item.get("aweme_id") or "")
                if not aweme_id or aweme_id in seen:
                    continue
                seen.add(aweme_id)
                inspected += 1
                if aweme_id in excluded:
                    continue
                await original_get_media(self, item)
                video_path = output_root / "douyin" / "videos" / aweme_id / "video.mp4"
                if not video_path.is_file() or video_path.stat().st_size <= 0:
                    continue
                captured.append(_candidate(item, rank=inspected, video_path=video_path))
                if len(captured) >= limit:
                    break
            page += 1

    crawler = DouYinCrawler()
    crawler.search = MethodType(search_selected, crawler)
    await crawler.start()
    return {"keyword": keyword, "candidates": captured}


def main() -> None:
    args = _arguments()
    input_path = Path(args.input).resolve()
    output_path = Path(args.output).resolve()
    payload = json.loads(input_path.read_text(encoding="utf-8"))
    result = asyncio.run(_run(payload))
    output_path.parent.mkdir(parents=True, exist_ok=True)
    output_path.write_text(json.dumps(result, ensure_ascii=False, indent=2), encoding="utf-8")


if __name__ == "__main__":
    main()
