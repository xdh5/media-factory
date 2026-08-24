"""统一视频发布常量。"""

from pathlib import Path

PROJECT_ROOT = Path(__file__).resolve().parents[3]
BEIJING_TIMEZONE = "Asia/Shanghai"
MATRIXMEDIA_EXECUTABLE_ENV = "MATRIXMEDIA_EXECUTABLE"
MATRIXMEDIA_DIR_ENV = "MATRIXMEDIA_DIR"
MATRIXMEDIA_TIMEOUT_SECONDS = 2400

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
MATRIXMEDIA_PLATFORM_CODES = {
    "douyin": "dy",
    "kuaishou": "ks",
    "baijiahao": "bjh",
    "toutiao": "tt",
    "wechat_channels": "sph",
}
MATRIXMEDIA_CODE_PLATFORMS = {
    **{value: key for key, value in MATRIXMEDIA_PLATFORM_CODES.items()},
    "抖音": "douyin",
    "快手": "kuaishou",
    "百家号": "baijiahao",
    "头条": "toutiao",
    "头条号": "toutiao",
    "视频号": "wechat_channels",
}
PUBLIC_URL_PLATFORMS = ("facebook", "instagram", "tiktok")
PUBLISH_MODES = ("immediate", "scheduled")
