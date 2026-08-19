"""文生图 MCP 错误定义。"""


class Text2ImageError(Exception):
    code = "TEXT2IMAGE_ERROR"

    def __init__(self, message: str, details: dict | None = None):
        super().__init__(message)
        self.message = message
        self.details = details or {}

    def to_dict(self) -> dict:
        return {"error": {"code": self.code, "message": self.message, "details": self.details}}


class AgentOutputFormatError(Text2ImageError):
    code = "AGENT_OUTPUT_FORMAT_ERROR"


class WorkflowStepError(Text2ImageError):
    code = "WORKFLOW_STEP_ERROR"


class ConfirmationRequiredError(Text2ImageError):
    code = "CONFIRMATION_REQUIRED"


class DraftNotFoundError(Text2ImageError):
    code = "DRAFT_NOT_FOUND"
