"""动漫拼接 MCP 错误。"""


class AnimeError(Exception):
    def __init__(self, message: str, details: dict | None = None):
        super().__init__(message)
        self.message = message
        self.details = details or {}


class WorkflowStepError(AnimeError):
    pass


class TaskNotFoundError(AnimeError):
    pass
