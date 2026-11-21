"""重点句大字图层公开入口。"""

from ._animations import ANIMATIONS, SUPPORTED_ANIMATIONS, entrance_tags
from ._detect import validate_emphasis_groups
from .generate_emphasis_lines import DEFAULT_SETTINGS, generate_emphasis_lines

__all__ = [
    "generate_emphasis_lines",
    "validate_emphasis_groups",
    "DEFAULT_SETTINGS",
    "ANIMATIONS",
    "SUPPORTED_ANIMATIONS",
    "entrance_tags",
]
