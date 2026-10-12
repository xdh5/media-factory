"""语言学习 MCP 成片制作编排。"""

from .api import (
    language_learning_create_videos,
    language_learning_start_create_videos,
)

MEDIA_TOOLS = (
    language_learning_create_videos,
    language_learning_start_create_videos,
)
