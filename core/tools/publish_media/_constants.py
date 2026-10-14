"""统一视频发布常量。"""

from pathlib import Path

PROJECT_ROOT = Path(__file__).resolve().parents[3]
BEIJING_TIMEZONE = "Asia/Shanghai"
MEDIA_PUBLISHER_EXECUTABLE_ENV = "MEDIA_PUBLISHER_EXECUTABLE"
MEDIA_PUBLISHER_DIR_ENV = "MEDIA_PUBLISHER_DIR"
MEDIA_PUBLISHER_TIMEOUT_SECONDS = 2400

BUSINESS_LINES = ("finance", "language_learning")
SUPPORTED_PLATFORMS = (
    "youtube",
    "facebook",
    "instagram",
    "tiktok",
    "kuaishou",
    "douyin",
    "baijiahao",
    "toutiao",
    "wechat_channels",
)
PLATFORM_ALIASES = {
    "youtube": "youtube",
    "yt": "youtube",
    "ytb": "youtube",
    "facebook": "facebook",
    "fb": "facebook",
    "instagram": "instagram",
    "ig": "instagram",
    "tiktok": "tiktok",
    "tk": "tiktok",
    "kuaishou": "kuaishou",
    "ks": "kuaishou",
    "快手": "kuaishou",
    "douyin": "douyin",
    "dy": "douyin",
    "抖音": "douyin",
    "baijiahao": "baijiahao",
    "bjh": "baijiahao",
    "百家号": "baijiahao",
    "toutiao": "toutiao",
    "tt": "toutiao",
    "头条": "toutiao",
    "头条号": "toutiao",
    "wechat_channels": "wechat_channels",
    "sph": "wechat_channels",
    "视频号": "wechat_channels",
}
MEDIA_PUBLISHER_PLATFORM_CODES = {
    "douyin": "dy",
    "baijiahao": "bjh",
    "kuaishou": "ks",
    "toutiao": "tt",
    "wechat_channels": "sph",
}
MEDIA_PUBLISHER_CODE_PLATFORMS = {
    **{value: key for key, value in MEDIA_PUBLISHER_PLATFORM_CODES.items()},
    "抖音": "douyin",
    "百家号": "baijiahao",
    "快手": "kuaishou",
    "头条": "toutiao",
    "头条号": "toutiao",
    "视频号": "wechat_channels",
}


def media_publisher_root() -> Path:
    """media-publisher 仓库根目录。"""
    import os

    override = os.getenv(MEDIA_PUBLISHER_DIR_ENV, "").strip()
    return Path(override or PROJECT_ROOT / "integrations" / "media-publisher").resolve()


def media_publisher_executable() -> str:
    """已安装的命令行程序。"""
    import os

    return os.getenv(MEDIA_PUBLISHER_EXECUTABLE_ENV, "").strip()


PUBLIC_URL_PLATFORMS = ("facebook", "instagram", "tiktok")
PUBLISH_MODES = ("immediate", "scheduled")
