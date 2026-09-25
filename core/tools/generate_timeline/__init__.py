"""生成章节时间轴条（ASS 覆盖图层）与 AI 章节标题。

财经成片的「上方/下方时间轴」：横条按章节分段，段落标题由 AI 生成，
当前时段标题高亮，进度色随播放时间从左往右推进。
"""

from ._errors import InvalidParameterError, TimelineError
from .generate_timeline import generate_chapter_timeline
from ._titles import fallback_chapter_titles, generate_chapter_titles

__all__ = [
    "generate_chapter_timeline",
    "generate_chapter_titles",
    "fallback_chapter_titles",
    "TimelineError",
    "InvalidParameterError",
]
