"""财经后台任务编排。"""
from __future__ import annotations
from ..infrastructure.gateways import RunnerTaskNotFoundError
from ..infrastructure.gateways import runner_poll_task
from ..errors import TaskNotFoundError

def finance_poll_task(task_path: str) -> dict:
    """轮询后台任务。status=succeeded 时读 result；failed 时读 error 并停止制作。"""
    try:
        return runner_poll_task(task_path=task_path)
    except RunnerTaskNotFoundError as exc:
        raise TaskNotFoundError(str(exc), {"task_path": task_path}) from exc

