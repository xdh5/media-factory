"""从成片第一帧导出 YouTube 独立封面。"""

from pathlib import Path

from core.tools.generate_final_video._ffmpeg import _executable, _run


def resolve_youtube_thumbnail(video_path: str | Path) -> Path:
    """优先使用制作时保存的封面，只有原图缺失时才截取首帧。"""
    video = Path(video_path).resolve()
    for name in ("cover.png", "cover.jpg", "cover.jpeg"):
        cover = video.parent / name
        if cover.is_file():
            if cover.stat().st_size < 2 * 1024 * 1024:
                return cover
            # 原图超出接口限制时只压缩原图，仍不从视频重新截图。
            from PIL import Image
            thumbnail = video.with_name(f"{video.stem}-youtube-thumbnail.jpg")
            with Image.open(cover) as image:
                image = image.convert("RGB")
                image.thumbnail((1280, 1280))
                image.save(thumbnail, quality=90, optimize=True)
            return thumbnail
    return extract_youtube_thumbnail(video)


def extract_youtube_thumbnail(video_path: str | Path) -> Path:
    """解码第零帧，保留合入视频的封面画面并限制上传文件大小。"""
    video = Path(video_path).resolve()
    thumbnail = video.with_name(f"{video.stem}-youtube-thumbnail.jpg")
    for quality in (2, 5, 10, 20, 31):
        _run([
            _executable("ffmpeg"), "-y", "-i", str(video),
            "-map", "0:v:0", "-frames:v", "1",
            "-vf", "scale=1280:1280:force_original_aspect_ratio=decrease",
            "-q:v", str(quality), str(thumbnail),
        ], "提取 YouTube 第一帧封面", timeout_seconds=60)
        if thumbnail.is_file() and 0 < thumbnail.stat().st_size < 2 * 1024 * 1024:
            return thumbnail
    raise ValueError("YouTube 第一帧封面必须小于 2 MiB")
