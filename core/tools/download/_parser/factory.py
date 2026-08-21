from .downloaders.xiaohongshu_downloader import XiaohongshuDownloader
from .downloaders.douyin_downloader import DouyinDownloader
from .downloaders.kuaishou_downloader import KuaishouDownloader
from .downloaders.bilibili_downloader import BilibiliDownloader
from .downloaders.haokan_downloader import HaokanDownloader
from .downloaders.weishi_downloader import WeishiDownloader
from .downloaders.lishipin_downloader import LishipinDownloader
from .downloaders.pipigaoxiao_downloader import PipigaoxiaoDownloader


class DownloaderFactory:
    platform_to_downloader = {
        "小红书": XiaohongshuDownloader,
        "抖音": DouyinDownloader,
        "快手": KuaishouDownloader,
        "哔哩哔哩": BilibiliDownloader,
        "好看视频": HaokanDownloader,
        "微视": WeishiDownloader,
        "梨视频": LishipinDownloader,
        "皮皮搞笑": PipigaoxiaoDownloader
    }

    @staticmethod
    def create_downloader(platform, real_url):
        downloader_class = DownloaderFactory.platform_to_downloader.get(platform)
        if downloader_class is None:
            raise ValueError(f"Unsupported platform: {platform}")
        return downloader_class(real_url)

