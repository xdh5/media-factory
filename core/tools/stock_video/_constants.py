"""正版视频素材搜索与下载常量。"""

PROVIDER_PRIORITY = ("pexels", "pixabay", "coverr")
PEXELS_API_URL = "https://api.pexels.com/v1/videos/search"
PIXABAY_API_URL = "https://pixabay.com/api/videos/"
COVERR_API_URL = "https://api.coverr.co/videos"
PEXELS_API_KEY_ENV = "PEXELS_API_KEY"
PIXABAY_API_KEY_ENV = "PIXABAY_API_KEY"
COVERR_API_KEY_ENV = "COVERR_API_KEY"
DEFAULT_TIMEOUT_SECONDS = 30
DEFAULT_RESULTS_PER_PROVIDER = 12
MAX_RESULTS_PER_PROVIDER = 40
SEARCH_CACHE_SECONDS = 24 * 60 * 60
MAX_DOWNLOAD_BYTES = 300 * 1024 * 1024
ALLOWED_DOWNLOAD_HOST_SUFFIXES = {
    "pexels": (".pexels.com", ".vimeo.com", ".vimeocdn.com", ".akamaized.net"),
    "pixabay": (".pixabay.com",),
    "coverr": (".coverr.co", ".cloudfront.net"),
}
ATTRIBUTION_URLS = {
    "pexels": "https://www.pexels.com",
    "pixabay": "https://pixabay.com",
    "coverr": "https://coverr.co",
}
