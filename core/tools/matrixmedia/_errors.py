"""MatrixMedia CLI Tool 错误定义。"""


class MatrixMediaToolError(Exception):
    code = "MATRIXMEDIA_TOOL_ERROR"

    def __init__(self, message: str, details: dict | None = None):
        super().__init__(message)
        self.message = message
        self.details = details or {}

    def to_dict(self) -> dict:
        return {"error": {"code": self.code, "message": self.message, "details": self.details}}


class InvalidParameterError(MatrixMediaToolError):
    code = "INVALID_PARAMETER"

    def __init__(self, parameter: str, message: str):
        super().__init__(message, {"parameter": parameter})


class CLIExecutableNotFoundError(MatrixMediaToolError):
    code = "CLI_EXECUTABLE_NOT_FOUND"


class CLIExecutionError(MatrixMediaToolError):
    code = "CLI_EXECUTION_FAILED"


class CLIOutputError(MatrixMediaToolError):
    code = "CLI_OUTPUT_INVALID"


class AccountDatabaseError(MatrixMediaToolError):
    code = "ACCOUNT_DATABASE_ERROR"


class AccountNotFoundError(MatrixMediaToolError):
    code = "ACCOUNT_NOT_FOUND"


class AccountGroupNotFoundError(MatrixMediaToolError):
    code = "ACCOUNT_GROUP_NOT_FOUND"
