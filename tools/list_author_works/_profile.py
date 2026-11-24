"""作者作品请求使用的浏览器指纹。必须和 DY_COOKIES 所属浏览器一致。"""

from __future__ import annotations

import os

_DEFAULTS = {
    "ua": (
        "Mozilla/5.0 (Windows NT 10.0; Win64; x64) AppleWebKit/537.36 "
        "(KHTML, like Gecko) Chrome/151.0.0.0 Safari/537.36"
    ),
    "browser_version": "151.0.0.0",
    "engine_version": "151.0.0.0",
    "screen_width": "2560",
    "screen_height": "1440",
    "cpu_core_num": "20",
    "device_memory": "32",
    "accept_language": "zh-CN,zh;q=0.9,en;q=0.8,zh-TW;q=0.7,ja;q=0.6",
}

_profile: dict | None = None


def _env(key: str, default: str) -> str:
    return os.getenv("DY_FP_" + key.upper()) or default


def _int_env(key: str, default: int) -> int:
    try:
        return int(_env(key, str(default)))
    except (TypeError, ValueError):
        return int(default)


def get_profile() -> dict:
    """返回进程内稳定的浏览器档案。"""
    global _profile
    if _profile is not None:
        return _profile
    ua = _env("ua", _DEFAULTS["ua"])
    major = _env("browser_version", _DEFAULTS["browser_version"]).split(".")[0]
    profile = {
        "ua": ua,
        "sec_ch_ua": (
            f'"Not=A?Brand";v="99", "Google Chrome";v="{major}", "Chromium";v="{major}"'
        ),
        "sec_ch_ua_platform": '"Windows"',
        "browser_name": "Chrome",
        "browser_version": _env("browser_version", _DEFAULTS["browser_version"]),
        "engine_name": "Blink",
        "engine_version": _env("engine_version", _DEFAULTS["engine_version"]),
        "cpu_core_num": _env("cpu_core_num", _DEFAULTS["cpu_core_num"]),
        "device_memory": _env("device_memory", _DEFAULTS["device_memory"]),
        "screen_width": _env("screen_width", _DEFAULTS["screen_width"]),
        "screen_height": _env("screen_height", _DEFAULTS["screen_height"]),
        "accept_language": _env("accept_language", _DEFAULTS["accept_language"]),
    }
    width = int(profile["screen_width"])
    height = int(profile["screen_height"])
    profile["geo"] = (
        _int_env("inner_width", width),
        _int_env("inner_height", height - 225),
        _int_env("outer_width", width),
        _int_env("outer_height", height - 48),
        _int_env("avail_width", width),
        _int_env("avail_height", height - 48),
        width,
        height,
    )
    _profile = profile
    return profile
