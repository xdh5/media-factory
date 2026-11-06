"""工作流错误映射与任务轮询。"""

from __future__ import annotations


from ..infrastructure import (
    MediaRecordsError,
    ImageGenerationError,
    MediaFilesError,
    RunnerTaskNotFoundError,
    TopicDedupError,
    runner_poll_task,
)

from ..errors import LanguageLearningError, TaskNotFoundError


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


def language_learning_poll_task(task_path: str) -> dict:
    """轮询后台任务。status=succeeded 时读 result；failed 时读 error 并停止制作。"""
    try:
        return runner_poll_task(task_path=task_path)
    except RunnerTaskNotFoundError as exc:
        raise TaskNotFoundError(str(exc), {"task_path": task_path}) from exc
