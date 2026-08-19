"""封面刻字工具公开入口。"""

from .generate_cover import generate_cover
from ._errors import CoverError

__all__ = ["generate_cover", "CoverError"]
