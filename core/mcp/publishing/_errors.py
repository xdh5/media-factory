"""统一发布 MCP 错误。"""


class PublishingError(Exception):
    """统一发布 MCP 基础错误。"""

    code = "PUBLISHING_ERROR"

    def __init__(self, message: str, details: dict | None = None):
        super().__init__(message)
        self.message = message
        self.details = details or {}


class PublishingRequestError(PublishingError):
    """发布请求不完整或不可执行。"""

    code = "PUBLISHING_REQUEST_ERROR"


class PublishingTaskNotFoundError(PublishingError):
    """发布后台任务不存在。"""

    code = "PUBLISHING_TASK_NOT_FOUND"
