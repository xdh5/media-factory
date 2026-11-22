"""正版视频素材搜索与下载常量。"""

PEXELS_API_URL = "https://api.pexels.com/v1/videos/search"
PEXELS_API_KEY_ENV = "PEXELS_API_KEY"
DEFAULT_TIMEOUT_SECONDS = 30
DEFAULT_RESULTS_PER_PROVIDER = 12
# 网站标注时长经常比真实文件略长，选片时比镜头实际需要多留 1 秒。
SELECTION_DURATION_MARGIN_SECONDS = 1
MAX_RESULTS_PER_PROVIDER = 40
SEARCH_CACHE_SECONDS = 24 * 60 * 60
MAX_DOWNLOAD_BYTES = 300 * 1024 * 1024
ALLOWED_DOWNLOAD_HOST_SUFFIXES = {
    "pexels": (".pexels.com", ".vimeo.com", ".vimeocdn.com", ".akamaized.net"),
}
ATTRIBUTION_URLS = {
    "pexels": "https://www.pexels.com",
}

# 素材规范化时在同一滤镜链中施加磨砂效果。
SOFT_BLUR_WHITE_ALPHA = 0.18
SOFT_BLUR_CONTRAST = 0.85
SOFT_BLUR_SATURATION = 0.78
