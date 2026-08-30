"""Cloudflare 数据服务常量。"""

CLOUDFLARE_DATA_API_URL_ENV = "CLOUDFLARE_DATA_API_URL"
CLOUDFLARE_DATA_API_TOKEN_ENV = "CLOUDFLARE_DATA_API_TOKEN"
DEFAULT_REQUEST_TIMEOUT_SECONDS = 30
DEFAULT_CURL_MAX_TIME_SECONDS = 30
CURL_MAX_ATTEMPTS = 5
CURL_RETRY_DELAY_SECONDS = 1
MAX_RESPONSE_BYTES = 4 * 1024 * 1024
PUBLICATION_BUSINESS_LINES = ("finance", "language_learning")
PUBLICATION_PLATFORMS = (
    "youtube",
    "facebook",
    "instagram",
    "tiktok",
    "kuaishou",
    "douyin",
    "baijiahao",
    "xiaohongshu",
    "toutiao",
    "wechat_channels",
)
PUBLICATION_MODES = ("immediate", "scheduled")
PUBLICATION_STATUSES = ("published", "scheduled")
PUBLISHING_CONNECTORS = ("youtube", "zernio", "matrixmedia")
PRODUCTION_BUSINESS_LINES = ("finance", "language_learning")
PRODUCTION_SOURCES = ("local_mcp", "github_workflow")
