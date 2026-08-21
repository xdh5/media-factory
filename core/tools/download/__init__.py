"""视频下载公开入口。"""

from ._errors import DownloadError
from .download import download

__all__ = [
    "download",
    "DownloadError",
]
