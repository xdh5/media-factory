"""向 MCP 宿主 Agent 暴露语言学习视频工作流。"""

from pathlib import Path
import warnings

from mcp.server.fastmcp import FastMCP

from core.tools.image import ImageGenerationError, prepare_agent_image_tasks
from core.tools.jobs import enqueue_job, get_job, recover_interrupted_jobs
from core.tools.run_cache import ConfirmationRequiredError as RunCacheConfirmationRequiredError, clear_run
from core.tools.topic_history import DuplicateTopicError, get_topic, update

from ._constants import (
    DEFAULT_DATABASE_PATH,
    JOB_HANDLER,
    SUBJECT_SHEET_IMAGE_ID,
    SUBJECT_SHEET_RADIO,
    SUBJECT_SHEET_SIZE_TEXT,
    TOPIC_DEDUPLICATION_DAYS,
    WORKFLOW_ID,
    production_dirs,
    production_run_id,
)
from ._errors import ConfirmationRequiredError, LanguageLearningError
from .tools.vocabulary import build_subject_sheet_prompt, build_vocabulary_prompt, parse_vocabulary_response

warnings.filterwarnings("ignore", message=r"Field 'lifespan' has an incomplete definition.*")

mcp = FastMCP(
    "media-factory-language-learning",
    instructions=(
        "执行语言学习视频工作流。先调用 language_learning_get_topics，根据返回的最近 30 天话题"
        "由当前 Agent 选一个不重复的主题，再调用 language_learning_build_vocabulary_prompt；"
        "按原样 Prompt 生成纯文本词表后调用 language_learning_parse_vocabulary_response；"
        "然后调用 language_learning_prepare_images。必须按返回任务优先使用当前宿主 Agent 自身能力生图，"
        "再调用 language_learning_submit_images；该工具立即返回 job_id，必须用 language_learning_get_job 查询；"
        "只有宿主无能力或单张失败三次才允许方舟兜底。"
        "完成后用 result.subject_sheet_path 调用 language_learning_compose_cards 分别制作中韩卡片，"
        "每次同样返回 job_id，用 language_learning_get_job 查询。"
        "再调用 language_learning_create_videos，用 language_learning_get_job 等到 completed。"
        "视频完成后必须向用户展示标题、标签和账号组，等待明确确认后再调用 language_learning_publish；"
        "发布也返回 job_id，用 language_learning_get_job 查询。"
        "发布结束后向用户确认是否删除本次生产文件，确认后调用 language_learning_clear_run。"
        "中文固定发布到 YouTube 账号组“学中文”。"
        "禁止绕过 MCP 自行生成主体图或直接读写工作流内部文件。"
    ),
)

recover_interrupted_jobs(WORKFLOW_ID, DEFAULT_DATABASE_PATH)


def _enqueue(job_type: str, payload: dict) -> dict:
    return enqueue_job(WORKFLOW_ID, job_type, payload, handler=JOB_HANDLER)


@mcp.tool()
def language_learning_get_topics(database_path: str | None = None) -> dict:
    """返回最近 30 天已占用的语言学习主题，供当前 Agent 避开重复后再写词表。"""
    database = Path(database_path or DEFAULT_DATABASE_PATH).resolve()
    recent = get_topic(database, WORKFLOW_ID, TOPIC_DEDUPLICATION_DAYS)
    return {
        "workflow": WORKFLOW_ID,
        "deduplication_days": TOPIC_DEDUPLICATION_DAYS,
        "recent_topics": [item["topic"] for item in recent],
        "next_tool": "language_learning_build_vocabulary_prompt",
    }


@mcp.tool()
def language_learning_build_vocabulary_prompt(
    topic: str,
    learning_modes: list[str],
    database_path: str | None = None,
) -> dict:
    """占用主题并返回词表 Prompt，由当前 Agent 按原样生成纯文本词表。"""
    database = Path(database_path or DEFAULT_DATABASE_PATH).resolve()
    try:
        record = update(database, WORKFLOW_ID, topic, TOPIC_DEDUPLICATION_DAYS)
    except DuplicateTopicError as exc:
        raise LanguageLearningError(str(exc), exc.details) from exc
    result = build_vocabulary_prompt(record["topic"], learning_modes)
    run_id = production_run_id(record["id"])
    run_dir, cache_root, output_root = production_dirs(run_id)
    cache_root.mkdir(parents=True, exist_ok=True)
    output_root.mkdir(parents=True, exist_ok=True)
    return {
        **result,
        "topic_record_id": record["id"],
        "run_id": run_id,
        "cache_dir": str(cache_root),
        "output_dir": str(output_root),
        "run_dir": str(run_dir),
        "next_tool": "language_learning_parse_vocabulary_response",
    }


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
    if not isinstance(force_images, bool):
        raise LanguageLearningError("force_images 必须是布尔值")
    sheet = build_subject_sheet_prompt(topic, words)
    _run_dir, cache_root, _output_root = production_dirs(run_id)
    cache_root = cache_root / "agent-images"
    try:
        result = prepare_agent_image_tasks(
            [{"image_id": SUBJECT_SHEET_IMAGE_ID, "kind": "image", "prompt": sheet["prompt"]}],
            None,
            SUBJECT_SHEET_RADIO,
            SUBJECT_SHEET_SIZE_TEXT,
            cache_root,
            exact_size=False,
            force_images=force_images,
            metadata={"workflow": "language_learning", "topic": sheet["topic"], "run_id": run_id},
        )
    except ImageGenerationError as exc:
        raise LanguageLearningError(exc.message, exc.details) from exc
    return {**result, "topic": sheet["topic"], "run_id": run_id, "next_tool": "language_learning_submit_images"}


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
    """用户明确确认后后台发布：中文到 YouTube「学中文」。立即返回 job_id。"""
    return _enqueue("publish", {
        "manifest_path": manifest_path,
        "publish_confirmed": publish_confirmed,
    })


@mcp.tool()
def language_learning_get_job(job_id: str, database_path: str | None = None) -> dict:
    """查询后台任务；queued/running 时稍后再查，completed 时使用 result，failed 时查看 error。"""
    return get_job(job_id, database_path, workflow=WORKFLOW_ID)


@mcp.tool()
def language_learning_clear_run(run_id: str, confirmed: bool) -> dict:
    """用户确认后删除本次生产目录，保留话题记录。"""
    try:
        return clear_run(WORKFLOW_ID, run_id, confirmed=confirmed)
    except RunCacheConfirmationRequiredError as exc:
        raise ConfirmationRequiredError(str(exc)) from exc


if __name__ == "__main__":
    mcp.run(transport="stdio")
