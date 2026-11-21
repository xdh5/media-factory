"""语言词包领取、词表校验与生产计划。"""

from __future__ import annotations
from datetime import date
import json, re, unicodedata
from tools.database._errors import DatabaseError
from tools.database.production_records import list_production_outputs
from tools.database.publication_records import list_publication_records
from workflows.language_learning.infrastructure.packs import list_recent_words as records_list_recent_words, claim_language_learning_pack, release_language_learning_pack
from workflows.language_learning.parameters import (
    MINIMUM_NEW_WORDS,
    SUPPORTED_LEARNING_MODES,
    WORD_HISTORY_DAYS,
    WORDS_PER_TASK,
    DEFAULT_PRODUCTION_CONFIG,
    PUBLISH_TAGS,
    SHORT_TITLE_TEMPLATES,
    video_content_kind,
    WORKFLOW_ID,
    normalize_publish_date,
    production_dirs,
    production_run_id,
)
from workflows.language_learning.errors.exceptions import VocabularyHistoryError, VocabularyReuseError
from copy import deepcopy
from tools.publish_media.local_assets import current_language_outputs
from workflows.language_learning.errors.mapping import _map_error


def normalize_english_word(value: str) -> str:
    """归一化英语单词：NFKC + 大小写折叠 + 弯引号替换 + 空白折叠，与词库入库口径一致。"""
    normalized = unicodedata.normalize("NFKC", str(value or "")).casefold().replace("’", "'")
    return re.sub(r"\s+", " ", normalized).strip()


def list_recent_words() -> list[str]:
    """返回 D1 最近 100 天使用过的英语词汇。"""
    try:
        return records_list_recent_words(WORD_HISTORY_DAYS)
    except DatabaseError as exc:
        raise VocabularyHistoryError(
            f"读取 Cloudflare D1 最近 {WORD_HISTORY_DAYS} 天单词历史失败：{exc.message}",
            exc.details,
        ) from exc


def _word_entries(words_by_mode: dict) -> list[dict]:
    entries: dict[str, dict] = {}
    for mode in SUPPORTED_LEARNING_MODES:
        for item in words_by_mode.get(mode) or []:
            english = str(item.get("english") or "").strip()
            normalized = normalize_english_word(english)
            if not normalized:
                raise VocabularyHistoryError(f"{mode} 词表存在空的英语单词")
            entry = entries.setdefault(
                normalized,
                {"english": english, "normalized_english": normalized, "modes": {}},
            )
            entry["modes"][mode] = dict(item)
    if len(entries) != WORDS_PER_TASK:
        raise VocabularyHistoryError(
            f"单词历史每次必须记录 {WORDS_PER_TASK} 个不同英语词，现在是 {len(entries)} 个"
        )
    return list(entries.values())


def build_database_word_entries(words_by_mode: dict) -> list[dict]:
    """生成随成片交付清单传递、待产出成功后入库的单词数据。"""
    return [
        {
            "english": entry["english"],
            "normalized_english": entry["normalized_english"],
            "word_json": json.dumps(entry, ensure_ascii=False, separators=(",", ":")),
        }
        for entry in _word_entries(words_by_mode)
    ]


def validate_words(*, run_id: str, topic: str, words_by_mode: dict) -> dict:
    """生产阶段只读取 D1 校验新词比例，不写入任何话题或单词。"""
    rid = str(run_id or "").strip()
    clean_topic = str(topic or "").strip()
    if not rid or not clean_topic:
        raise VocabularyHistoryError("校验单词历史时 run_id 和 topic 不能为空")
    if re.fullmatch(r"run-(\d{6,})", rid) is None:
        raise VocabularyHistoryError(f"run_id 格式不正确：{rid}")
    entries = _word_entries(words_by_mode)
    try:
        recent = {normalize_english_word(word) for word in records_list_recent_words(WORD_HISTORY_DAYS)}
    except DatabaseError as exc:
        raise VocabularyHistoryError(
            f"读取 Cloudflare D1 单词历史失败：{exc.message}",
            exc.details,
        ) from exc
    repeated_words = [entry["english"] for entry in entries if entry["normalized_english"] in recent]
    new_word_count = len(entries) - len(repeated_words)
    if new_word_count < MINIMUM_NEW_WORDS:
        raise VocabularyReuseError(
            f"本次只有 {new_word_count} 个新词；{WORDS_PER_TASK} 个单词中至少需要 "
            f"{MINIMUM_NEW_WORDS} 个未在最近 {WORD_HISTORY_DAYS} 天使用",
            {
                "history_days": WORD_HISTORY_DAYS,
                "minimum_new_words": MINIMUM_NEW_WORDS,
                "new_word_count": new_word_count,
                "repeated_word_count": len(repeated_words),
                "repeated_words": repeated_words,
            },
        )
    return {
        "recorded": False,
        "pending_publish": True,
        "run_id": rid,
        "word_count": len(entries),
        "new_word_count": new_word_count,
        "repeated_word_count": len(repeated_words),
        "repeated_words": repeated_words,
        "history_days": WORD_HISTORY_DAYS,
        "minimum_new_words": MINIMUM_NEW_WORDS,
    }


def language_learning_get_production_config(topic: str = "", learning_modes: list[str] | None = None) -> dict:
    """返回 Agent 与 GitHub Runner 共用的语言学习固定生产参数。"""
    config = deepcopy(DEFAULT_PRODUCTION_CONFIG)
    modes = list(learning_modes or config["learning_modes"])
    clean_topic = str(topic or "").strip()
    publish_config = {}
    if "en-zh" in modes:
        publish_config["en-zh"] = {
            "tags": list(PUBLISH_TAGS["en-zh"]),
            "short_title": SHORT_TITLE_TEMPLATES["en-zh"].format(topic=clean_topic),
        }
    if "en-ko" in modes:
        publish_config["en-ko"] = {
            "tags": list(PUBLISH_TAGS["en-ko"]),
            "short_title": SHORT_TITLE_TEMPLATES["en-ko"],
        }
    config["learning_modes"] = modes
    config["publish_config"] = publish_config
    return config


def language_learning_get_automation_plan(publish_date: str) -> dict:
    """返回 GitHub 生产与发布工作流共用的预检结果。"""
    try:
        normalized_date = normalize_publish_date(publish_date)
        outputs = current_language_outputs(list_production_outputs(publish_date=normalized_date, business_line=WORKFLOW_ID))
        publications = list_publication_records(business_line=WORKFLOW_ID, publish_date=normalized_date)
        github_outputs = [row for row in outputs if row.get("source") == "github_workflow" and row.get("r2_url")]
        existing_run_id = str(github_outputs[0].get("run_id") or "") if github_outputs else ""
        published = {
            (str(row["publication_id"]).split(":")[-2], str(row["platform"]), int(row.get("content_part") or 1))
            for row in publications
            if ":" in str(row.get("publication_id") or "")
        }
        publishable = [row for row in (github_outputs or outputs) if row["content_kind"] in {"en-zh", "en-zh-quiz"}]
        targets = list(DEFAULT_PRODUCTION_CONFIG["publish_targets"])
        pending = [
            target for target in targets
            if any((row["content_kind"], target, int(row.get("content_part") or 1)) not in published for row in publishable)
        ]
        expected = [
            {"learning_mode": mode, "video_format": video_format, "content_part": 1}
            for mode in DEFAULT_PRODUCTION_CONFIG["learning_modes"]
            for video_format in DEFAULT_PRODUCTION_CONFIG["video_formats"]
        ]
        existing_kinds = {row["content_kind"] for row in outputs if int(row["content_part"]) == 1}
        pending_outputs = [item for item in expected if video_content_kind(item["learning_mode"], item["video_format"]) not in existing_kinds]
        should_generate = bool(pending_outputs)
        return {
            "publish_date": normalized_date,
            "should_generate": should_generate,
            "pending_outputs": pending_outputs,
            "completed_outputs": github_outputs,
            "desired_output_count": len(expected),
            "should_resume_publish": not should_generate and bool(existing_run_id) and bool(pending),
            "existing_run_id": existing_run_id,
            "pending_targets": pending,
            "publish_targets": targets,
            "skip_reason": "" if should_generate else f"该计划发布日期已有 {len(outputs)} 条成片记录、{len(publications)} 条发布记录",
        }
    except Exception as exc:
        raise _map_error(exc) from exc


def language_learning_get_production_outputs(publish_date: str) -> dict:
    """查询某个北京时间计划发布日期的语言学习成片。"""
    try:
        return {
            "publish_date": publish_date,
            "business_line": WORKFLOW_ID,
            "records": list_production_outputs(
                publish_date=publish_date,
                business_line=WORKFLOW_ID,
            ),
        }
    except Exception as exc:
        raise _map_error(exc) from exc


def language_learning_claim_pack(publish_date: str) -> dict:
    """为 GitHub 生产领取一个包含十张已验收透明主体图的词包。"""
    try:
        run_id = production_run_id(publish_date)
        pack = claim_language_learning_pack(run_id=run_id, publish_date=publish_date)
        cache_root, output_root = production_dirs(run_id)
        cache_root.mkdir(parents=True, exist_ok=True); output_root.mkdir(parents=True, exist_ok=True)
        return {"run_id": run_id, "publish_date": publish_date, "cache_dir": str(cache_root), "output_dir": str(output_root), "pack": pack}
    except Exception as exc:
        raise _map_error(exc) from exc


def language_learning_release_pack(publish_date: str) -> dict:
    """失败或中断时归还词包；已经完整交付的生产保留使用记录。"""
    try:
        normalized_date = date.fromisoformat(str(publish_date).strip()).isoformat()
        return release_language_learning_pack(run_id=f"run-{normalized_date.replace('-', '')}", publish_date=normalized_date)
    except Exception as exc:
        raise _map_error(exc) from exc
