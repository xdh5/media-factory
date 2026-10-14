"""收集财经文案的错误。"""


class CollectFinanceCopyError(Exception):
    code = "COLLECT_FINANCE_COPY_ERROR"

    def __init__(self, message: str, details: dict | None = None):
        super().__init__(message)
        self.message = message
        self.details = details or {}

    def to_dict(self) -> dict:
        return {"error": {"code": self.code, "message": self.message, "details": self.details}}


class CollectCopyError(CollectFinanceCopyError):
    code = "COLLECT_FINANCE_COPY_FAILED"
