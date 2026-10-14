"""财经后台任务和清理编排。"""
from __future__ import annotations
from ..infrastructure.gateways import ClearCacheConfirmationRequiredError
from ..infrastructure.gateways import clear_run
from ..infrastructure.gateways import RunnerTaskNotFoundError
from ..infrastructure.gateways import runner_poll_task
from ..config.settings import MCP_ID
from ..errors import ConfirmationRequiredError, TaskNotFoundError

def finance_poll_task(task_path: str) -> dict:
    """轮询后台任务。status=succeeded 时读 result；failed 时读 error 并停止制作。"""
    try:
        return runner_poll_task(task_path=task_path)
    except RunnerTaskNotFoundError as exc:
        raise TaskNotFoundError(str(exc), {"task_path": task_path}) from exc


def finance_clear_run(run_id: str, confirmed: bool) -> dict:
    """用户确认后删除本次生产目录（cache 和成品），保留话题库记录。"""
    try:
        return clear_run(MCP_ID, run_id, confirmed=confirmed)
    except ClearCacheConfirmationRequiredError as exc:
        raise ConfirmationRequiredError(str(exc)) from exc

