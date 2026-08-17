"""财经工作流错误定义。"""


class FinanceWorkflowError(Exception):
    code = "FINANCE_WORKFLOW_ERROR"

    def __init__(self, message: str, details: dict | None = None):
        super().__init__(message)
        self.message = message
        self.details = details or {}

    def to_dict(self) -> dict:
        return {"error": {"code": self.code, "message": self.message, "details": self.details}}


class AgentTextCapabilityError(FinanceWorkflowError):
    code = "AGENT_TEXT_CAPABILITY_ERROR"


class AgentOutputFormatError(FinanceWorkflowError):
    code = "AGENT_OUTPUT_FORMAT_ERROR"


class WorkflowStepError(FinanceWorkflowError):
    code = "WORKFLOW_STEP_ERROR"


class ProductNotFoundError(FinanceWorkflowError):
    code = "PRODUCT_NOT_FOUND"


class ProductDeletionError(FinanceWorkflowError):
    code = "PRODUCT_DELETION_ERROR"
