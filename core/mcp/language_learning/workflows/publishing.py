"""语言学习 MCP 上传与发布编排。"""

from .api import (
    language_learning_record_publications,
    language_learning_start_publish,
    language_learning_start_upload_r2,
)

PUBLISHING_TOOLS = (
    language_learning_record_publications,
    language_learning_start_upload_r2,
    language_learning_start_publish,
)
