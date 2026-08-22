"""财经 MCP 错误定义。"""


class FinanceError(Exception):
    code = "FINANCE_ERROR"

    def __init__(self, message: str, details: dict | None = None):
        super().__init__(message)
        self.message = message
        self.details = details or {}

    def to_dict(self) -> dict:
        return {"error": {"code": self.code, "message": self.message, "details": self.details}}


class AgentOutputFormatError(FinanceError):
    code = "AGENT_OUTPUT_FORMAT_ERROR"


class WorkflowStepError(FinanceError):
    code = "WORKFLOW_STEP_ERROR"


class ConfirmationRequiredError(FinanceError):
    code = "CONFIRMATION_REQUIRED"


class DraftNotFoundError(FinanceError):
    code = "DRAFT_NOT_FOUND"


class TaskNotFoundError(FinanceError):
    code = "TASK_NOT_FOUND"
