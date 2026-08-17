"""向 Trae 暴露 Finance 工作流的 stdio MCP Server。"""

from __future__ import annotations

import warnings

# mcp 依赖当前会从 pydantic-settings 输出一条无害的 lifespan 前向引用告警；
# stdio MCP 只保留协议消息和真正的运行错误，避免污染 Trae 的服务日志。
warnings.filterwarnings(
    "ignore",
    message=r"Field 'lifespan' has an incomplete definition.*",
)

from mcp.server.fastmcp import FastMCP

from core.workflows.finance.trae_adapter import (
    finish_video,
    get_draft_context,
    prepare_storyboard,
    publish_product,
    save_draft,
)


mcp = FastMCP(
    "media-factory-finance",
    instructions=(
        "只执行 Finance 视频工作流。必须在稿件生成后等待用户确认；"
        "确认后自动制作视频；最终发布前必须再次等待用户明确确认。"
    ),
)


@mcp.tool()
def finance_get_draft_context(database_path: str | None = None) -> dict:
    """读取近 30 天话题和稿件 Prompt；Trae 应使用自己的模型生成话题、正文、标题与标签。"""
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
    """用户明确确认稿件后生成 TTS，并返回 Trae 生成分镜所需的 Prompt 和时间轴。"""
    return prepare_storyboard(draft_path, user_confirmed=user_confirmed)


@mcp.tool()
def finance_finish_video(
    draft_path: str,
    storyboard_text: str,
    user_confirmed: bool,
    force_shot_ids: list[str] | None = None,
    force_images: bool = False,
) -> dict:
    """使用 Trae 生成的分镜自动完成生图、镜头、封面、字幕、BGM 和成品入库。"""
    return finish_video(
        draft_path,
        storyboard_text,
        user_confirmed=user_confirmed,
        force_shot_ids=force_shot_ids,
        force_images=force_images,
    )


@mcp.tool()
def finance_publish(
    manifest_path: str,
    publish_confirmed: bool,
    account_group_name: str = "心灵鸡汤",
) -> dict:
    """用户明确确认本次发布后，把成品发布到 MatrixMedia 账号组。"""
    return publish_product(
        manifest_path,
        publish_confirmed=publish_confirmed,
        account_group_name=account_group_name,
    )


if __name__ == "__main__":
    mcp.run(transport="stdio")
