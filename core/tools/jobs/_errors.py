"""后台任务工具错误定义。"""


class JobError(Exception):
    code = "JOB_ERROR"

    def __init__(self, message: str, details: dict | None = None):
        super().__init__(message)
        self.message = message
        self.details = details or {}

    def to_dict(self) -> dict:
        return {"error": {"code": self.code, "message": self.message, "details": self.details}}


class InvalidParameterError(JobError):
    code = "INVALID_PARAMETER"

    def __init__(self, parameter: str, message: str):
        super().__init__(message, {"parameter": parameter})


class JobNotFoundError(JobError):
    code = "JOB_NOT_FOUND"


class JobExecutionError(JobError):
    code = "JOB_EXECUTION_ERROR"
