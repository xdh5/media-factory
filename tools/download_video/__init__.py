"""分享链接下载。"""

from ._errors import DownloadError
from ._urlutil import extract_url, extract_urls
from .download import download

__all__ = [
    "download",
    "DownloadError",
    "extract_url",
    "extract_urls",
]
