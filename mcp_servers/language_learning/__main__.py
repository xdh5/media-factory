"""语言学习 MCP：`python -m mcp_servers.language_learning`。"""

from __future__ import annotations

import warnings

warnings.filterwarnings(
    "ignore",
    message=r"Field 'lifespan' has an incomplete definition.*",
)

from mcp.server.fastmcp import FastMCP

from core.tools.jobs import enqueue_job, get_job, recover_interrupted_jobs, wait_task

from ._constants import (
    CHINESE_PUBLISH_ACCOUNT_GROUP,
    DEFAULT_DATABASE_PATH,
    JOB_HANDLER,
    KOREAN_PUBLISH_ACCOUNT_GROUP,
    WORKFLOW_ID,
)
from .tools.session import (
    clear_language_learning_run,
    get_topics,
    occupy_topic_and_build_prompt,
    prepare_images,
    save_images,
)
from .tools.vocabulary import parse_vocabulary_response

mcp = FastMCP(
    "media-factory-language-learning",
    instructions=(
        "执行语言学习视频。先调用 language_learning_get_topics，根据返回的最近 30 天话题"
        "由当前 Agent 选一个不重复的主题，再调用 language_learning_build_vocabulary_prompt；"
        "按原样 Prompt 生成纯文本词表后调用 language_learning_parse_vocabulary_response；"
        "然后调用 language_learning_prepare_images。必须按返回任务优先使用当前宿主 Agent 自身能力生图，"
        "每生成一张立刻调用 language_learning_save_images 写入缓存；"
        "再调用 language_learning_submit_images；该工具立即返回 job_id，必须用 language_learning_wait_task 等到终态；"
        "只有宿主无能力或单张失败三次才允许方舟兜底。"
        "完成后用 result.subject_sheet_path 调用 language_learning_compose_cards 分别制作中韩卡片，"
        "每次同样返回 job_id，用 language_learning_wait_task 等到 completed。"
        "再调用 language_learning_create_videos，用 language_learning_wait_task 等到 completed。"
        f"视频完成后必须向用户展示成片路径、标题、标签和账号组（中文 YouTube「{CHINESE_PUBLISH_ACCOUNT_GROUP}」以及 Facebook/Instagram Reels、韩语「{KOREAN_PUBLISH_ACCOUNT_GROUP}」），等用户看过成品并明确确认后再发布；"
        "未确认不得调用 language_learning_publish，也不得调矩媒。"
        "确认后：中文调用 language_learning_publish（返回 job_id，用 language_learning_wait_task 查询；会发 YouTube 和 Meta Reels）；"
        f"韩语改调 MatrixMedia MCP，按账号组「{KOREAN_PUBLISH_ACCOUNT_GROUP}」逐个 publish_video；未登录的抖音/视频号先 login 把二维码发给用户扫。"
        "发布结束后向用户确认是否删除本次生产文件，确认后调用 language_learning_clear_run。"
        "禁止绕过 MCP 自行生成主体图或直接读写 MCP 内部文件。"
    ),
)

recover_interrupted_jobs(WORKFLOW_ID, DEFAULT_DATABASE_PATH)


def _enqueue(job_type: str, payload: dict) -> dict:
    return enqueue_job(WORKFLOW_ID, job_type, payload, handler=JOB_HANDLER)


@mcp.tool()
def language_learning_get_topics(database_path: str | None = None) -> dict:
    """返回最近 30 天已占用的语言学习主题，供当前 Agent 避开重复后再写词表。"""
    return get_topics(database_path)


@mcp.tool()
def language_learning_build_vocabulary_prompt(
    topic: str,
    learning_modes: list[str],
    database_path: str | None = None,
) -> dict:
    """占用主题并返回词表 Prompt，由当前 Agent 按原样生成纯文本词表。"""
    return occupy_topic_and_build_prompt(topic, learning_modes, database_path)


@mcp.tool()
def language_learning_parse_vocabulary_response(response_text: str, learning_modes: list[str]) -> dict:
    """严格解析 Agent 生成的词表；格式错误时返回可修正的具体原因。"""
    return parse_vocabulary_response(response_text, learning_modes)


@mcp.tool()
def language_learning_prepare_images(
    topic: str,
    words: list[dict],
    run_id: str,
    force_images: bool = False,
) -> dict:
    """返回 16:9 透明 2×5 主体图任务；无画风参考图，像素不必正好 1920×1080。"""
    return prepare_images(topic, words, run_id, force_images)


@mcp.tool()
def language_learning_save_images(context_path: str, images: list[dict]) -> dict:
    """把已生成的主体图立刻写入本次生产缓存。"""
    return save_images(context_path, images)


@mcp.tool()
def language_learning_submit_images(
    context_path: str,
    images: list[dict],
    failures: list[dict] | None = None,
) -> dict:
    """提交主体图到后台；无能力或失败三次才走方舟。立即返回 job_id。"""
    return _enqueue("submit_images", {
        "context_path": context_path,
        "images": images,
        "failures": failures,
    })


@mcp.tool()
def language_learning_compose_cards(
    subject_sheet_path: str,
    words: list[dict],
    learning_mode: str,
    topic_english: str,
    run_id: str,
) -> dict:
    """后台把主体图按 2 行×5 列贴到单词卡。立即返回 job_id。"""
    return _enqueue("compose_cards", {
        "subject_sheet_path": subject_sheet_path,
        "words": words,
        "learning_mode": learning_mode,
        "topic_english": topic_english,
        "run_id": run_id,
    })


@mcp.tool()
def language_learning_create_videos(
    card_dirs: dict[str, str],
    words_by_mode: dict,
    run_id: str,
    topic: str = "",
    language_pause: float = 0.3,
    word_pause: float = 0.3,
) -> dict:
    """后台生成中韩学习视频。立即返回 job_id。"""
    return _enqueue("create_videos", {
        "card_dirs": card_dirs,
        "words_by_mode": words_by_mode,
        "run_id": run_id,
        "topic": topic,
        "language_pause": language_pause,
        "word_pause": word_pause,
    })


@mcp.tool()
def language_learning_publish(manifest_path: str, publish_confirmed: bool) -> dict:
    """用户看过成片并明确确认后，后台发布中文到 YouTube 与 Facebook/Instagram Reels。立即返回 job_id。韩语不走本工具。"""
    return _enqueue("publish", {
        "manifest_path": manifest_path,
        "publish_confirmed": publish_confirmed,
    })


@mcp.tool()
def language_learning_get_job(job_id: str, database_path: str | None = None) -> dict:
    """瞬时查询后台任务，不阻塞。等待终态请用 language_learning_wait_task。"""
    return get_job(job_id, database_path, workflow=WORKFLOW_ID)


@mcp.tool()
def language_learning_wait_task(
    job_id: str,
    database_path: str | None = None,
    timeout: float | None = None,
) -> dict:
    """阻塞等到任务 completed/failed（最长 180 秒）。仍在运行则再调一次。完成后读 result，失败看 error。"""
    return wait_task(job_id, database_path, workflow=WORKFLOW_ID, timeout=timeout)


@mcp.tool()
def language_learning_clear_run(run_id: str, confirmed: bool) -> dict:
    """用户确认后删除本次生产目录，保留话题记录。"""
    return clear_language_learning_run(run_id, confirmed=confirmed)


if __name__ == "__main__":
    mcp.run(transport="stdio")
