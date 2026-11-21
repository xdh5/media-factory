"""语言学习工作流错误转换。"""

from __future__ import annotations


from tools.database._errors import DatabaseError
from tools.r2_files import R2FilesError
from tools.database._errors import TopicHistoryError

from workflows.language_learning.errors.exceptions import LanguageLearningError


def _map_error(exc: Exception) -> LanguageLearningError:
    if isinstance(exc, LanguageLearningError):
        return exc
    if isinstance(exc, TopicHistoryError):
        return LanguageLearningError(str(exc), exc.details)
    if isinstance(exc, R2FilesError):
        return LanguageLearningError(exc.message, exc.details)
    if isinstance(exc, DatabaseError):
        return LanguageLearningError(exc.message, exc.details)
    raise exc
