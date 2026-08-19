"""文生图 MCP：`python -m mcp_servers.text2image`。业务线（画风、BGM、写稿、账号）由 workflows 提供。"""

from __future__ import annotations

import warnings

warnings.filterwarnings(
    "ignore",
    message=r"Field 'lifespan' has an incomplete definition.*",
)

from mcp.server.fastmcp import FastMCP

from core.tools.jobs import enqueue_job, get_job, recover_interrupted_jobs, wait_task

from .agent_images import prepare_agent_images, save_agent_images
from ._constants import DEFAULT_DATABASE_PATH, JOB_HANDLER
from ._line import list_line_ids, load_line
from .draft import clear_text2image_run, get_draft_context, save_draft

mcp = FastMCP(
    "media-factory-text2image",
    instructions=(
        "只执行文生图视频管线。必须传入业务线 line（如 finance）；画风、BGM、旁白和发布账号组由该线固定，Agent 不得改。"
        "必须在稿件生成后等待用户确认；确认后自动制作视频；成品完成后必须先向用户展示成片路径、标题和文案并等待确认，"
        "用户确认后再用 MatrixMedia MCP 按 result.matrixmedia_account_group 逐个发布；"
        "publish_video 的 file 必须用 result.video_path，禁止复制改名为 publish.mp4；"
        "未登录时抖音/视频号调用 login 把二维码图片发给用户扫码，再用 login_status 等到成功；"
        "发完再向用户确认是否删除本次生产文件，确认后调用 text2image_clear_run。"
        "耗时工具会立即返回 job_id，必须用 text2image_wait_task 等到 completed 或 failed；"
        "text2image_get_job 只做瞬时快照。禁止绕过 MCP 运行本地脚本。"
        "finance 线镜头从图库抽取：text2image_prepare_images 若返回 image_source=library 或全部 needs_generation=false，"
        "禁止宿主生图，直接调用 text2image_submit_images（images 可空列表）。"
        "其它业务线必须按 text2image_prepare_images 返回的任务优先使用当前宿主 Agent 自身能力生图，"
        "每生成一张立刻调用 text2image_save_images 写入缓存；全部就绪或需要方舟兜底时再调用 text2image_submit_images。"
        "只有宿主无能力或单张失败三次才允许方舟兜底。"
    ),
)

for _line_id in list_line_ids():
    recover_interrupted_jobs(_line_id, DEFAULT_DATABASE_PATH)


def _enqueue(line: str, job_type: str, payload: dict) -> dict:
    selected = load_line(line)
    return enqueue_job(selected.id, job_type, payload, handler=JOB_HANDLER)


@mcp.tool()
def text2image_get_draft_context(line: str, database_path: str | None = None) -> dict:
    """读取指定业务线近 30 天话题和稿件 Prompt；当前 Agent 应使用自己的模型生成话题、正文、标题与标签。"""
    return get_draft_context(line, database_path)


@mcp.tool()
def text2image_save_draft(
    line: str,
    topic: str,
    article: str,
    title: str,
    short_title: str,
    hashtags: list[str],
    database_path: str | None = None,
    draft_path: str | None = None,
) -> dict:
    """保存完整稿件并返回确认材料；调用后必须停止，等待用户明确确认。"""
    return save_draft(line, topic, article, title, short_title, hashtags, database_path, draft_path)


@mcp.tool()
def text2image_prepare_storyboard(draft_path: str, user_confirmed: bool) -> dict:
    """提交 TTS 与分镜上下文后台任务；立即返回 job_id，不会阻塞 MCP。"""
    from .draft import load_draft

    _resolved, draft = load_draft(draft_path, "待确认稿件")
    return _enqueue(
        str(draft.get("line") or ""),
        "prepare_storyboard",
        {"draft_path": draft_path, "user_confirmed": user_confirmed},
    )


@mcp.tool()
def text2image_prepare_images(
    draft_path: str,
    storyboard_text: str,
    user_confirmed: bool,
    force_image_ids: list[str] | None = None,
    force_images: bool = False,
) -> dict:
    """返回镜头图任务。finance 从图库抽图，全部命中后不要生图，直接 submit。"""
    return prepare_agent_images(
        draft_path,
        storyboard_text,
        user_confirmed=user_confirmed,
        force_image_ids=force_image_ids,
        force_images=force_images,
    )


@mcp.tool()
def text2image_save_images(context_path: str, images: list[dict]) -> dict:
    """把已生成的图片立刻写入本次生产缓存，同步返回仍缺哪些图。"""
    return save_agent_images(context_path, images)


@mcp.tool()
def text2image_submit_images(
    context_path: str,
    images: list[dict],
    failures: list[dict] | None = None,
) -> dict:
    """后台接收生图结果；无能力或失败三次的单张图片才会调用方舟。立即返回 job_id。"""
    from .draft import load_draft

    _resolved, context = load_draft(context_path, "生图上下文")
    metadata = context.get("metadata") if isinstance(context.get("metadata"), dict) else {}
    line = str(metadata.get("line") or context.get("line") or "")
    return _enqueue(
        line,
        "submit_images",
        {"context_path": context_path, "images": images, "failures": failures},
    )


@mcp.tool()
def text2image_finish_video(
    draft_path: str,
    image_manifest_path: str,
    user_confirmed: bool,
    storyboard_text: str | None = None,
    force_shot_ids: list[str] | None = None,
) -> dict:
    """用已提交的生图清单启动后台视频合成；分镜以 prepare_images 保存的为准，不必再传。立即返回 job_id。"""
    from .draft import load_draft

    _resolved, draft = load_draft(draft_path, "待确认稿件")
    payload = {
        "draft_path": draft_path,
        "image_manifest_path": image_manifest_path,
        "user_confirmed": user_confirmed,
        "force_shot_ids": force_shot_ids,
    }
    if storyboard_text:
        payload["storyboard_text"] = storyboard_text
    return _enqueue(str(draft.get("line") or ""), "finish_video", payload)


@mcp.tool()
def text2image_get_job(job_id: str, database_path: str | None = None) -> dict:
    """瞬时查询后台任务，不阻塞。等待终态请用 text2image_wait_task。"""
    return get_job(job_id, database_path)


@mcp.tool()
def text2image_wait_task(
    job_id: str,
    database_path: str | None = None,
    timeout: float | None = None,
) -> dict:
    """阻塞等到任务 completed/failed（最长 180 秒）。仍在运行则再调一次。完成后读 result，失败看 error。"""
    return wait_task(job_id, database_path, timeout=timeout)


@mcp.tool()
def text2image_clear_run(line: str, run_id: str, confirmed: bool) -> dict:
    """用户确认后删除本次生产目录（cache 和成品），保留话题库记录。"""
    return clear_text2image_run(line, run_id, confirmed=confirmed)


if __name__ == "__main__":
    mcp.run(transport="stdio")
