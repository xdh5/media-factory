"""从分享口令或链接解析出平台真实视频地址。"""

from __future__ import annotations

from ._errors import InvalidParameterError, ParseLinkError
from ._parser.service import ParserError, ParserService

__all__ = ["parse_link"]

_PARSE_HINTS = {
    "No valid video URL found": "分享内容里没有有效视频链接。请传入含 http/https 的抖音、快手、小红书、B 站等分享口令或链接",
    "Unsupported video URL": "不支持该平台链接。请确认是抖音、快手、小红书、哔哩哔哩、好看视频、微视、梨视频或皮皮搞笑",
}


def parse_link(share_text: str) -> dict:
    """解析分享文字或链接，返回平台、标题和真实 video_url。"""
    text = str(share_text or "").strip()
    if not text:
        raise InvalidParameterError("share_text", "share_text 不能为空，请粘贴平台分享口令或视频链接")
    try:
        parsed = ParserService().parse(text)
    except ParserError as exc:
        hint = _PARSE_HINTS.get(str(exc))
        if hint:
            raise ParseLinkError(hint, {"share_text": text}) from exc
        if "Parse failed" in str(exc) or "DOUYIN_COOKIE" in str(exc):
            raise ParseLinkError(
                "解析失败：拿不到平台视频地址。抖音请在 .env 填写有效 DOUYIN_COOKIE 后重试",
                {"share_text": text},
            ) from exc
        raise ParseLinkError(f"解析失败：{exc}", {"share_text": text}) from exc
    except Exception as exc:
        raise ParseLinkError(f"解析失败：{type(exc).__name__}: {exc}", {"share_text": text}) from exc
    result = {
        "video_id": parsed.get("video_id") or "",
        "platform": parsed.get("platform") or "",
        "title": parsed.get("title"),
        "video_url": parsed.get("video_url") or "",
        "cover_url": parsed.get("cover_url"),
    }
    if parsed.get("audio_url"):
        result["audio_url"] = parsed["audio_url"]
    if not result["video_url"]:
        raise ParseLinkError("解析成功但没有 video_url，请换一条链接或检查该平台是否可匿名解析")
    return result
