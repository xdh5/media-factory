"""语言学习工作流错误转换。"""

from __future__ import annotations


from tools.media_records import MediaRecordsError
from tools.generate_image import ImageGenerationError
from tools.media_files import MediaFilesError
from tools.topic_dedup import TopicDedupError

from workflows.language_learning.errors.exceptions import LanguageLearningError


def _map_error(exc: Exception) -> LanguageLearningError:
    if isinstance(exc, LanguageLearningError):
        return exc
    if isinstance(exc, ImageGenerationError):
        return LanguageLearningError(exc.message, exc.details)
    if isinstance(exc, TopicDedupError):
        return LanguageLearningError(str(exc), exc.details)
    if isinstance(exc, MediaFilesError):
        return LanguageLearningError(exc.message, exc.details)
    if isinstance(exc, MediaRecordsError):
        return LanguageLearningError(exc.message, exc.details)
    raise exc
