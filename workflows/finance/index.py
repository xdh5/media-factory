"""向 MCP 宿主 Agent 暴露财经视频工作流。"""

from __future__ import annotations

import warnings

warnings.filterwarnings(
    "ignore",
    message=r"Field 'lifespan' has an incomplete definition.*",
)

from mcp.server.fastmcp import FastMCP

from core.tools.jobs import enqueue_job, get_job, recover_interrupted_jobs

from ._agent_images import prepare_agent_images
from ._constants import DEFAULT_DATABASE_PATH, JOB_HANDLER, WORKFLOW_ID
from .tools.draft import clear_finance_run, get_draft_context, save_draft

mcp = FastMCP(
    "media-factory-finance",
    instructions=(
        "只执行 Finance 视频工作流。必须在稿件生成后等待用户确认；"
        "确认后自动制作视频；成品完成后必须先向用户展示成片路径、标题和文案并等待确认，"
        "用户确认后再用 MatrixMedia MCP 按账号组「心灵鸡汤」逐个发布；"
        "发完再向用户确认是否删除本次生产文件，确认后调用 finance_clear_run。"
        "耗时工具会返回 job_id，必须用 finance_get_job 查询，禁止绕过 MCP 运行本地脚本。"
        "必须按 finance_prepare_images 返回的任务优先使用当前宿主 Agent 自身能力生图，"
        "再调用 finance_submit_images 提交结果；只有宿主无能力或单张失败三次才允许方舟兜底。"
    ),
)

recover_interrupted_jobs(WORKFLOW_ID, DEFAULT_DATABASE_PATH)


def _enqueue(job_type: str, payload: dict) -> dict:
    return enqueue_job(WORKFLOW_ID, job_type, payload, handler=JOB_HANDLER)


@mcp.tool()
def finance_get_draft_context(database_path: str | None = None) -> dict:
    """读取近 30 天话题和稿件 Prompt；当前 Agent 应使用自己的模型生成话题、正文、标题与标签。"""
    return get_draft_context(database_path)


@mcp.tool()
def finance_save_draft(
    topic: str,
    article: str,
    title: str,
    short_title: str,
    hashtags: list[str],
    database_path: str | None = None,
    draft_path: str | None = None,
) -> dict:
    """保存完整稿件并返回确认材料；调用后必须停止，等待用户明确确认。"""
    return save_draft(topic, article, title, short_title, hashtags, database_path, draft_path)


@mcp.tool()
def finance_prepare_storyboard(draft_path: str, user_confirmed: bool) -> dict:
    """提交 TTS 与分镜上下文后台任务；立即返回 job_id，不会阻塞 MCP。"""
    return _enqueue("prepare_storyboard", {"draft_path": draft_path, "user_confirmed": user_confirmed})


@mcp.tool()
def finance_prepare_images(
    draft_path: str,
    storyboard_text: str,
    user_confirmed: bool,
    force_image_ids: list[str] | None = None,
    force_images: bool = False,
) -> dict:
    """返回当前 Agent 生图任务；每项都包含提示词、油画参考图、尺寸和目标路径。"""
    return prepare_agent_images(
        draft_path,
        storyboard_text,
        user_confirmed=user_confirmed,
        force_image_ids=force_image_ids,
        force_images=force_images,
    )


@mcp.tool()
def finance_submit_images(
    context_path: str,
    images: list[dict],
    failures: list[dict] | None = None,
) -> dict:
    """后台接收生图结果；无能力或失败三次的单张图片才会调用方舟。立即返回 job_id。"""
    return _enqueue("submit_images", {"context_path": context_path, "images": images, "failures": failures})


@mcp.tool()
def finance_finish_video(
    draft_path: str,
    storyboard_text: str,
    image_manifest_path: str,
    user_confirmed: bool,
    force_shot_ids: list[str] | None = None,
) -> dict:
    """使用当前 Agent 已提交的图片启动后台视频合成；立即返回 job_id。"""
    return _enqueue("finish_video", {
        "draft_path": draft_path,
        "storyboard_text": storyboard_text,
        "image_manifest_path": image_manifest_path,
        "user_confirmed": user_confirmed,
        "force_shot_ids": force_shot_ids,
    })


@mcp.tool()
def finance_get_job(job_id: str, database_path: str | None = None) -> dict:
    """查询后台任务；queued/running 时稍后再查，completed 时使用 result，failed 时查看 error。"""
    return get_job(job_id, database_path, workflow=WORKFLOW_ID)


@mcp.tool()
def finance_clear_run(run_id: str, confirmed: bool) -> dict:
    """用户确认后删除本次生产目录（cache 和成品），保留话题库记录。"""
    return clear_finance_run(run_id, confirmed=confirmed)


if __name__ == "__main__":
    mcp.run(transport="stdio")
