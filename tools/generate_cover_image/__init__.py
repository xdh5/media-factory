"""生成封面图片公开入口。"""

from .generate_cover_image import generate_cover_image
from ._errors import CoverError

__all__ = ["generate_cover_image", "CoverError"]
