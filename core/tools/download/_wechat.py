"""微信视频号解析：腾讯元宝两步接口。

移植自 xingchen-video-download 的 app/wechat.py（原移植自 ltaoo/wx_channels_download），
async httpx 改为同步 requests。
两步流程：
1) POST yuanbao.tencent.com get_parse_result -> wx_export_id + playable_url
2) POST channels.weixin.qq.com get_feed_info -> videoUrl / coverUrl / author
第 1 步需要有效的元宝登录 Cookie（环境变量 SPH_COOKIE）。
"""

from __future__ import annotations

import json
import logging
import random
import time
from dataclasses import dataclass, field
from urllib.parse import parse_qs, urlparse

import requests

logger = logging.getLogger("media-factory.download.wechat")


def _https(url: str) -> str:
    """http 统一升级 https，避免混用内容被拦截。"""
    if url and url.startswith("http://"):
        return "https://" + url[len("http://"):]
    return url


PARSE_URL = "https://yuanbao.tencent.com/api/weixin/get_parse_result"
FEED_INFO_URL = "https://channels.weixin.qq.com/finder-preview/api/feed/get_feed_info"

UA = ("Mozilla/5.0 (Macintosh; Intel Mac OS X 10_15_7) "
      "AppleWebKit/537.36 (KHTML, like Gecko) Chrome/148.0.0.0 Safari/537.36")

PARSE_HEADERS = {
    "accept": "application/json, text/plain, */*",
    "accept-language": "zh-CN,zh;q=0.9,en;q=0.8",
    "content-type": "application/json",
    "origin": "https://yuanbao.tencent.com",
    "referer": "https://yuanbao.tencent.com/chat/naQivTmsDa/cf4d0079-ed1b-4c55-a3f3-2ca1379727d1",
    "user-agent": UA,
    "sec-ch-ua": '"Chromium";v="148", "Google Chrome";v="148", "Not/A)Brand";v="99"',
    "sec-ch-ua-mobile": "?0",
    "sec-ch-ua-platform": '"macOS"',
    "sec-fetch-dest": "empty",
    "sec-fetch-mode": "cors",
    "sec-fetch-site": "same-origin",
    "t-userid": "b9575f6b0a8c4a55a08096904a5ef20a",
    "x-agentid": "naQivTmsDa/cf4d0079-ed1b-4c55-a3f3-2ca1379727d1",
    "x-commit-tag": "72282a0d",
    "x-device-id": "1921b001708100d7fa31002b9646bd0cc15a3e2e1f",
    "x-hy106": "",
    "x-hy92": "e963067ffa31002b9646bd0c03000008b1951a",
    "x-hy93": "1921b001708100d7fa31002b9646bd0cc15a3e2e1f",
    "x-id": "b9575f6b0a8c4a55a08096904a5ef20a",
    "x-instance-id": "5",
    "x-language": "zh-CN",
    "x-os_version": "Mac OS(10.15.7)-Blink",
    "x-platform": "mac",
    "x-requested-with": "XMLHttpRequest",
    "x-source": "web",
    "x-web-third-source": "main",
    "x-webdriver": "0",
    "x-webversion": "2.69.0",
    "x-ybuitest": "0",
}

FEED_HEADERS = {
    "Accept": "application/json, text/plain, */*",
    "Accept-Language": "zh-CN,zh;q=0.9,en;q=0.8",
    "Connection": "keep-alive",
    "Content-Type": "application/json",
    "Origin": "https://channels.weixin.qq.com",
    "Sec-Fetch-Dest": "empty",
    "Sec-Fetch-Mode": "cors",
    "Sec-Fetch-Site": "same-origin",
    "User-Agent": UA,
    "sec-ch-ua": '"Chromium";v="148", "Google Chrome";v="148", "Not/A)Brand";v="99"',
    "sec-ch-ua-mobile": "?0",
    "sec-ch-ua-platform": '"macOS"',
}


@dataclass
class VideoInfo:
    """视频号解析结果；headers 是下载时必须回放的防盗链请求头。"""

    title: str
    author: str
    author_avatar: str
    cover_url: str
    video_url: str
    video_id: str = ""
    duration: float | None = None
    width: int | None = None
    height: int | None = None
    ext: str = "mp4"
    source: str = "wechat_channels"
    headers: dict[str, str] = field(default_factory=dict)


def _gen_rid() -> str:
    ts = format(int(time.time()), "x")
    rand = "".join(random.choice("0123456789abcdef") for _ in range(8))
    return f"{ts}-{rand}"


def _clean_video_url(video_url: str) -> str:
    """只保留 encfilekey + token 两个查询参数（对应 Go 版 cleanVideoURL）。"""
    if not video_url:
        return ""
    parsed = urlparse(video_url)
    query = parse_qs(parsed.query)
    filekey = query.get("encfilekey", [""])[0]
    token = query.get("token", [""])[0]
    if filekey and token:
        base = f"{parsed.scheme}://{parsed.netloc}{parsed.path}"
        return f"{base}?encfilekey={filekey}&token={token}"
    return video_url


def _extract_from_parse(playable_url: str) -> tuple[str, str]:
    query = parse_qs(urlparse(playable_url).query)
    return query.get("token", [""])[0], query.get("eid", [""])[0]


def _parse_share_url(session: requests.Session, share_url: str, cookie: str) -> dict:
    payload = json.dumps({"type": "video_channel_url", "url": share_url, "scene": 1})
    headers = {**PARSE_HEADERS, "cookie": cookie}
    response = session.post(PARSE_URL, data=payload.encode("utf-8"), headers=headers, timeout=20)
    response.raise_for_status()
    data = response.json()
    if not data.get("data") or not data["data"].get("wx_export_id"):
        raise ValueError("解析分享链接失败:腾讯元宝未返回 wx_export_id")
    return data["data"]


def _get_feed_info(session: requests.Session, export_id: str, token: str) -> dict:
    rid = _gen_rid()
    payload = json.dumps({"baseReq": {"generalToken": token}, "exportId": export_id})
    api = (f"{FEED_INFO_URL}?_rid={rid}"
           "&_pageUrl=https:%2F%2Fchannels.weixin.qq.com%2Ffinder-preview%2Fpages%2Ffeed")
    referer = ("https://channels.weixin.qq.com/finder-preview/pages/feed"
               "?entry_card_type=48&comment_scene=39&appid=0"
               f"&token={token}&entry_scene=0&eid={export_id}")
    headers = {**FEED_HEADERS, "Referer": referer}
    response = session.post(api, data=payload.encode("utf-8"), headers=headers, timeout=20)
    response.raise_for_status()
    return response.json()


def fetch_video(share_url: str, cookie: str) -> VideoInfo:
    if not cookie:
        raise ValueError("未配置视频号 Cookie (SPH_COOKIE)。请在 .env 设置后重试。")
    session = requests.Session()
    parse_data = _parse_share_url(session, share_url, cookie)
    token, export_id = _extract_from_parse(parse_data.get("playable_url", ""))
    feed = _get_feed_info(session, export_id, token)

    fd = feed.get("data", {}).get("feedInfo", {})
    ad = feed.get("data", {}).get("authorInfo", {})
    raw_url = (fd.get("videoUrl", "")
               or fd.get("h265VideoInfo", {}).get("videoUrl", "")
               or fd.get("h264VideoInfo", {}).get("videoUrl", ""))
    video_url = _clean_video_url(raw_url)
    if not video_url:
        raise ValueError("未能从视频号接口提取到视频地址")
    # 视频号 CDN 校验 channels.weixin.qq.com 的 Referer。
    return VideoInfo(
        title=fd.get("description", "") or parse_data.get("desc", "") or "微信视频号视频",
        author=ad.get("nickname", "") or parse_data.get("author", ""),
        author_avatar=_https(ad.get("headImgUrl", "") or parse_data.get("author_icon", "")),
        cover_url=_https(fd.get("coverUrl", "") or parse_data.get("cover_url", "")),
        video_url=video_url,
        video_id=export_id,
        ext="mp4",
        source="wechat_channels",
        headers={
            "User-Agent": UA,
            "Referer": "https://channels.weixin.qq.com/",
        },
    )
