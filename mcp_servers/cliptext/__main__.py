"""公有剪辑转文字 MCP：`python -m mcp_servers.cliptext`。"""

from __future__ import annotations

import warnings

warnings.filterwarnings(
    "ignore",
    message=r"Field 'lifespan' has an incomplete definition.*",
)

from mcp.server.fastmcp import FastMCP

from core.tools.cliptext import (
    DEFAULT_DATABASE_PATH,
    JOB_HANDLER,
    JOB_NAMESPACE,
    parse_link,
)
from core.tools.jobs import enqueue_job, get_job, recover_interrupted_jobs, wait_task

mcp = FastMCP(
    "media-factory-cliptext",
    instructions=(
        "公有工具：只做链接解析和视频转文字。"
        "先用 cliptext_parse_link 解析分享口令或链接，再用返回的 video_url 调用 cliptext_transcribe。"
        "本地文件可直接 cliptext_transcribe。"
        "cliptext_transcribe 立即返回 job_id，必须用 cliptext_wait_task 等到终态；"
        "cliptext_get_job 只做瞬时快照。"
        "completed 时 result.text 是 Whisper 原文，不要自行改错别字。"
        "禁止绕过 MCP 直接调内部实现。"
    ),
)

recover_interrupted_jobs(JOB_NAMESPACE, DEFAULT_DATABASE_PATH)


@mcp.tool()
def cliptext_parse_link(share_text: str) -> dict:
    """从分享口令或链接解析平台、标题和真实视频地址。"""
    return parse_link(share_text)


@mcp.tool()
def cliptext_transcribe(media_path: str, language: str = "zh", filename: str = "") -> dict:
    """后台把音视频转成文字，立即返回 job_id。不做错别字校对。"""
    return enqueue_job(
        JOB_NAMESPACE,
        "transcribe",
        {"media_path": media_path, "language": language, "filename": filename},
        handler=JOB_HANDLER,
    )


@mcp.tool()
def cliptext_get_job(job_id: str, database_path: str | None = None) -> dict:
    """瞬时查询后台转写任务，不阻塞。等待终态请用 cliptext_wait_task。"""
    return get_job(job_id, database_path, workflow=JOB_NAMESPACE)


@mcp.tool()
def cliptext_wait_task(
    job_id: str,
    database_path: str | None = None,
    timeout: float | None = None,
) -> dict:
    """阻塞等到转写 completed/failed（最长 180 秒）。仍在运行则再调一次。completed 时读 result.text。"""
    return wait_task(job_id, database_path, workflow=JOB_NAMESPACE, timeout=timeout)


if __name__ == "__main__":
    mcp.run(transport="stdio")
