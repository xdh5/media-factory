"""视频下载常量。"""

from pathlib import Path

_PROJECT_ROOT = Path(__file__).resolve().parents[3]
DEFAULT_VIDEO_DIR = _PROJECT_ROOT / "data" / "download" / "videos"

DOWNLOAD_TIMEOUT_SECONDS = 600
DOWNLOAD_CONNECT_TIMEOUT_SECONDS = 30
MUX_TIMEOUT_SECONDS = 120
PLATFORM_REFERER = {
    "抖音": "https://www.douyin.com/",
    "快手": "https://www.kuaishou.com/",
    "小红书": "https://www.xiaohongshu.com/",
    "哔哩哔哩": "https://www.bilibili.com/",
    "好看视频": "https://haokan.baidu.com/",
    "微视": "https://isee.weishi.qq.com/",
    "梨视频": "https://www.pearvideo.com/",
    "皮皮搞笑": "https://h5.pipigx.com/",
}
DEFAULT_REFERER = "https://www.douyin.com/"
