"""财经工作流错误转换。"""
from __future__ import annotations
from tools.media_records import MediaRecordsError
from tools.media_files import MediaFilesError
from tools.topic_dedup import TopicDedupError
from workflows.finance.errors.exceptions import FinanceError, WorkflowStepError

def _map_error(exc: Exception) -> FinanceError:
    if isinstance(exc, FinanceError):
        return exc
    if isinstance(exc, TopicDedupError):
        return WorkflowStepError(str(exc), exc.details)
    if isinstance(exc, MediaFilesError):
        return WorkflowStepError(exc.message, exc.details)
    if isinstance(exc, MediaRecordsError):
        details = dict(exc.details)
        remote_code = str(getattr(exc, "remote_code", "")).strip()
        if remote_code:
            details["remote_code"] = remote_code
        return WorkflowStepError(exc.message, details)
    raise exc
