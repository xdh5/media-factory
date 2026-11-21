"""财经业务异常定义。"""


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


class DraftNotFoundError(FinanceError):
    code = "DRAFT_NOT_FOUND"


class TaskNotFoundError(FinanceError):
    code = "TASK_NOT_FOUND"


class CoverError(FinanceError):
    code = "COVER_ERROR"


class CoverParameterError(CoverError):
    code = "INVALID_PARAMETER"

    def __init__(self, parameter: str, message: str):
        super().__init__(message, {"parameter": parameter})


class CoverSourceImageError(CoverError):
    code = "COVER_SOURCE_IMAGE_ERROR"


class CoverFontError(CoverError):
    code = "COVER_FONT_ERROR"


class CoverRenderError(CoverError):
    code = "COVER_RENDER_ERROR"
