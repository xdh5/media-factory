"""从分享口令文本中提取真实链接并识别平台。

移植自 xingchen-video-download 的 app/urlutil.py。
"""

from __future__ import annotations

import re

# 匹配 http(s) 链接，遇到空白或中日韩字符即截断，避免把分享口令尾巴带进来。
_URL_RE = re.compile(
    r"https?://[^\s<>\u4e00-\u9fff\u3000-\u303f\uff00-\uffef\"']+",
    re.IGNORECASE,
)

# 常见短链与主站域名，用于平台识别。
_DOUYIN_HOSTS = ("v.douyin.com", "www.iesdouyin.com", "www.douyin.com")
_BILI_HOSTS = ("b23.tv", "www.bilibili.com", "bilibili.com", "m.bilibili.com")
_WEIBO_HOSTS = ("weibo.com", "www.weibo.com", "m.weibo.cn")
_XHS_HOSTS = ("www.xiaohongshu.com", "xiaohongshu.com", "xhslink.com")
_YT_HOSTS = ("www.youtube.com", "youtube.com", "youtu.be", "m.youtube.com")
_TT_HOSTS = ("www.tiktok.com", "tiktok.com")
_KS_HOSTS = ("kuaishou.com", "chenzhongtech.com", "gifshow.com", "kuaishouapp.com", "kwai.com")
_WX_HOSTS = ("weixin.qq.com",)


def _clean_url(url: str) -> str:
    return url.rstrip(".,;:!?)】》〉>\"'*")


def extract_urls(text: str) -> list[str]:
    """按出现顺序提取分享文本中的全部链接。"""
    if not text:
        return []
    return [_clean_url(matched.group(0)) for matched in _URL_RE.finditer(text) if _clean_url(matched.group(0))]


def extract_url(text: str) -> str:
    """从任意分享文本中提取第一条链接，识别不到返回空字符串。"""
    urls = extract_urls(text)
    return urls[0] if urls else ""


def detect_platform(url: str) -> str:
    """根据链接主机名尽力识别平台，识别不了返回 auto。"""
    host = url.lower()
    if any(h in host for h in _WX_HOSTS):
        return "wechat"
    if any(h in host for h in _DOUYIN_HOSTS):
        return "douyin"
    if any(h in host for h in _BILI_HOSTS):
        return "bilibili"
    if any(h in host for h in _WEIBO_HOSTS):
        return "weibo"
    if any(h in host for h in _XHS_HOSTS):
        return "xhs"
    if any(h in host for h in _YT_HOSTS):
        return "youtube"
    if any(h in host for h in _TT_HOSTS):
        return "tiktok"
    if any(h in host for h in _KS_HOSTS):
        return "kuaishou"
    return "auto"
