"""工作流错误映射与任务轮询。"""

from __future__ import annotations


from tools.media_records import MediaRecordsError
from tools.generate_image import ImageGenerationError
from tools.media_files import MediaFilesError
from tools.task_runner import TaskNotFoundError as RunnerTaskNotFoundError
from tools.topic_dedup import TopicDedupError
from tools.task_runner import poll_task as runner_poll_task

from workflows.language_learning.errors.exceptions import LanguageLearningError, TaskNotFoundError


from workflows.language_learning.errors.mapping import _map_error


def language_learning_poll_task(task_path: str) -> dict:
    """轮询后台任务。status=succeeded 时读 result；failed 时读 error 并停止制作。"""
    try:
        return runner_poll_task(task_path=task_path)
    except RunnerTaskNotFoundError as exc:
        raise TaskNotFoundError(str(exc), {"task_path": task_path}) from exc
