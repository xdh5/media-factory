"""跨工作流后台任务。公开只暴露提交、查询、等待终态和中断恢复。"""

from .jobs import enqueue_job, get_job, recover_interrupted_jobs, wait_task
from ._errors import JobNotFoundError

__all__ = ["enqueue_job", "get_job", "wait_task", "recover_interrupted_jobs", "JobNotFoundError"]
