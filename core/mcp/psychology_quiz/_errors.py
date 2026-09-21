"""心理测试 MCP 错误。"""


class PsychologyQuizError(Exception):
    code = "PSYCHOLOGY_QUIZ_ERROR"

    def __init__(self, message: str, details: dict | None = None):
        super().__init__(message)
        self.message = message
        self.details = details or {}


class WorkflowStepError(PsychologyQuizError):
    code = "WORKFLOW_STEP_ERROR"


class AgentOutputFormatError(PsychologyQuizError):
    code = "AGENT_OUTPUT_FORMAT_ERROR"


class ConfirmationRequiredError(PsychologyQuizError):
    code = "CONFIRMATION_REQUIRED"


class TaskNotFoundError(PsychologyQuizError):
    code = "TASK_NOT_FOUND"
