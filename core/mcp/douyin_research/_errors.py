"""抖音研究 MCP 错误。"""


class DouyinResearchMCPError(Exception):
    pass


class WorkflowStepError(DouyinResearchMCPError):
    def __init__(self, message: str, details: dict | None = None):
        super().__init__(message)
        self.details = details or {}


class TaskNotFoundError(DouyinResearchMCPError):
    pass
