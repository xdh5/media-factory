"""财经后台任务编排。"""
from __future__ import annotations
from tools.task_runner import TaskNotFoundError as RunnerTaskNotFoundError
from tools.task_runner import poll_task as runner_poll_task
from workflows.finance.errors.exceptions import TaskNotFoundError

def finance_poll_task(task_path: str) -> dict:
    """轮询后台任务。status=succeeded 时读 result；failed 时读 error 并停止制作。"""
    try:
        return runner_poll_task(task_path=task_path)
    except RunnerTaskNotFoundError as exc:
        raise TaskNotFoundError(str(exc), {"task_path": task_path}) from exc

