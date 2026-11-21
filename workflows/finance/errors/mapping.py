"""财经工作流错误转换。"""
from __future__ import annotations
from tools.database._errors import DatabaseError
from tools.r2_files import R2FilesError
from tools.database._errors import TopicHistoryError
from workflows.finance.errors.exceptions import FinanceError, WorkflowStepError

def _map_error(exc: Exception) -> FinanceError:
    if isinstance(exc, FinanceError):
        return exc
    if isinstance(exc, TopicHistoryError):
        return WorkflowStepError(str(exc), exc.details)
    if isinstance(exc, R2FilesError):
        return WorkflowStepError(exc.message, exc.details)
    if isinstance(exc, DatabaseError):
        details = dict(exc.details)
        remote_code = str(getattr(exc, "remote_code", "")).strip()
        if remote_code:
            details["remote_code"] = remote_code
        return WorkflowStepError(exc.message, details)
    raise exc
