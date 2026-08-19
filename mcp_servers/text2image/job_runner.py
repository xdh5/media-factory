"""文生图后台任务在独立进程中的执行入口。"""

from .agent_images import submit_agent_images
from ._errors import WorkflowStepError
from .draft import prepare_storyboard
from .engine import finish_video


def run_job(job_type: str, payload: dict) -> dict:
    if job_type == "prepare_storyboard":
        return prepare_storyboard(
            payload["draft_path"],
            user_confirmed=payload["user_confirmed"],
        )
    if job_type == "submit_images":
        return submit_agent_images(
            payload["context_path"],
            payload["images"],
            payload.get("failures"),
        )
    if job_type == "finish_video":
        return finish_video(
            payload["draft_path"],
            payload.get("storyboard_text"),
            image_manifest_path=payload["image_manifest_path"],
            user_confirmed=payload["user_confirmed"],
            force_shot_ids=payload.get("force_shot_ids"),
        )
    raise WorkflowStepError(f"不支持的文生图后台任务类型：{job_type}")
