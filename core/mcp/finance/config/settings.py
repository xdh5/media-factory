"""财经 MCP 技术常量（业务 Prompt 与参数见财经 Skill）。"""

from datetime import date, datetime
from pathlib import Path
from zoneinfo import ZoneInfo

from core.paths import (
    PROJECT_DATA_ROOT as PROJECT_DATA_ROOT,
    PROJECT_CACHE_ROOT as PROJECT_CACHE_ROOT,
    PROJECT_OUTPUT_ROOT as PROJECT_OUTPUT_ROOT,
    PROJECT_TMP_ROOT as PROJECT_TMP_ROOT,
)

MCP_ID = "finance"
SOURCE_COLLECTION_CODE = "finance"
SOURCE_RESERVATION_MINUTES = 120
DRAFT_FILE_NAME = "draft.json"
STORYBOARD_CONTEXT_FILE_NAME = "storyboard-context.json"
STORYBOARD_TEXT_FILE_NAME = "storyboard.txt"

TOPIC_DEDUPLICATION_DAYS = 30
VIDEO_SIZE = "1920x1080"
VIDEO_RADIO = "16:9"
CONTENT_KIND = "finance"
AUTOMATION_DAILY_OUTPUT_COUNT = 2

# 正文在两类必做改动（品牌替换、连载指涉改写）之外允许措辞级改写。
# 原稿入库前已补标点并修正错别字，制作时视为文字和标点正确。
# 但大结构与信息量必须与原稿一致；
# 每行上限约两行字幕容量（显示层再按词边界均衡换行），只挡超长行。
ARTICLE_MAX_LINE_LENGTH = 36
ARTICLE_MIN_CHARACTERS = 700
ARTICLE_MAX_CHARACTERS = 900
SOURCE_MIN_CHARACTERS = ARTICLE_MIN_CHARACTERS - 300
SOURCE_MAX_CHARACTERS = ARTICLE_MAX_CHARACTERS + 300

# 素材策略：实拍视频是默认来源，参考图宿主生图仍可指定。
MATERIAL_AGENT_REFERENCE = "agent_reference"    # 用户参考图 + 宿主逐镜头生图
MATERIAL_STOCK_VIDEO = "stock_video"          # Pexels/Pixabay/Coverr 正版实拍视频
MATERIAL_STRATEGIES = (
    MATERIAL_STOCK_VIDEO,
    MATERIAL_AGENT_REFERENCE,
)

# Finance MCP 是生产参数的唯一真源；Agent 与 GitHub Runner 均通过
# finance_get_config 获取，禁止在各自入口复制参数。
DEFAULT_PRODUCTION_CONFIG = {
    "material_strategy": MATERIAL_STOCK_VIDEO,
    "tts_config": {
        "voice": "fish:28df7fe4d3ec45f692af03d0a372805b",
        "rate": "+10%",
        "trim_trailing_silence": True,
    },
    "video_config": {
        "orientation": "landscape",
        "per_provider": 8,
        "providers": ["pexels", "pixabay", "coverr"],
        "soft_blur_sigma": 0.55,
    },
    "production_config": {
        "bgm_path": "core/static/bgm/easy-lemon-kevin-macleod.mp3",
        "bgm_gain": 0.672,
        "cover_frame_seconds": 0.03333333333333333,
        "intro": "slide_in_shutter",
        "shot_stickers": ["rec"],
    },
    "runner_retry_config": {
        "storyboard": 3,
        "editorial": 3,
    },
}

_ROOT = Path(__file__).resolve().parent.parent
STORYBOARD_PROMPT_PATH = _ROOT / "prompts" / "storyboard.md"


COLLECTION_CACHE_ROOT = PROJECT_CACHE_ROOT / "collect_finance_copy"
GENERATED_IMAGE_LIBRARY_ROOT = PROJECT_DATA_ROOT / "image_library_finance"
BEIJING_TIMEZONE = ZoneInfo("Asia/Shanghai")


def normalize_publish_date(publish_date: str) -> str:
    """校验北京时间计划发布日期，返回 YYYY-MM-DD。"""
    value = str(publish_date or "").strip()
    try:
        resolved = date.fromisoformat(value)
    except ValueError as exc:
        raise ValueError("publish_date 必须是 YYYY-MM-DD，例如 2026-08-25") from exc
    today = datetime.now(BEIJING_TIMEZONE).date()
    if resolved < today:
        raise ValueError(f"publish_date 不能早于北京时间当天 {today.isoformat()}")
    return resolved.isoformat()


def production_run_id(publish_date: str) -> str:
    """按北京时间计划发布日期生成 run-YYYYMMDD。"""
    normalized = normalize_publish_date(publish_date)
    return f"run-{normalized.replace('-', '')}"


def publish_date_from_run_id(run_id: str) -> str:
    """从新格式 run-YYYYMMDD 还原北京时间计划发布日期。"""
    value = str(run_id or "").strip()
    if len(value) != 12 or not value.startswith("run-") or not value[4:].isdigit():
        raise ValueError("run_id 必须是 run-YYYYMMDD，例如 run-20260825")
    raw = value[4:]
    try:
        return date(int(raw[:4]), int(raw[4:6]), int(raw[6:8])).isoformat()
    except ValueError as exc:
        raise ValueError(f"run_id 包含无效日期：{value}") from exc


def production_dirs(run_id: str, content_part: int = 1) -> tuple[Path, Path]:
    """本次生产目录：(cache_dir, output_dir)。

    同一天第二条及以后（content_part >= 2）使用 run-YYYYMMDD-partN 后缀目录；
    run_id 本身保持 run-YYYYMMDD，供 D1 唯一键 (run_id, content_part) 使用。
    """
    rid = str(run_id).strip()
    part = int(content_part or 1)
    suffix = "" if part <= 1 else f"-part{part}"
    return (
        PROJECT_CACHE_ROOT / MCP_ID / f"{rid}{suffix}",
        PROJECT_OUTPUT_ROOT / MCP_ID / f"{rid}{suffix}",
    )
