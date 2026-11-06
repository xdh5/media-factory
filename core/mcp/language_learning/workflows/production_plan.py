"""固定生产配置、产物查询与自动化预检。"""

from __future__ import annotations

from copy import deepcopy


from ..infrastructure import (
    list_production_outputs,
    list_publication_records,
)

from ..config import (
    DEFAULT_PRODUCTION_CONFIG,
    WORDS_PER_TASK,
    WORDS_PER_VIDEO,
    video_content_kind,
    WORKFLOW_ID,
    normalize_publish_date,
)
from .tasks import _map_error


def language_learning_get_production_config(topic: str = "", learning_modes: list[str] | None = None) -> dict:
    """返回 Agent 与 GitHub Runner 共用的语言学习固定生产参数。"""
    config = deepcopy(DEFAULT_PRODUCTION_CONFIG)
    modes = list(learning_modes or config["learning_modes"])
    clean_topic = str(topic or "").strip()
    publish_config = {}
    if "en-zh" in modes:
        publish_config["en-zh"] = {
            "tags": ["#learnchinese", "#chinesevocabulary", "#mandarinchinese", "#dailychinese"],
            "short_title": f"中文{clean_topic}怎么说",
        }
    if "en-ko" in modes:
        publish_config["en-ko"] = {
            "tags": ["#学韩语", "#韩语单词", "#韩语入门", "#每日韩语"],
            "short_title": "韩语单词怎么说",
        }
    config["learning_modes"] = modes
    config["publish_config"] = publish_config
    return config


def language_learning_get_automation_plan(publish_date: str) -> dict:
    """返回 GitHub 生产与发布工作流共用的预检结果。"""
    try:
        normalized_date = normalize_publish_date(publish_date)
        outputs = list_production_outputs(publish_date=normalized_date, business_line=WORKFLOW_ID)
        publications = list_publication_records(business_line=WORKFLOW_ID, publish_date=normalized_date)
        github_outputs = [row for row in outputs if row.get("source") == "github_workflow" and row.get("r2_url")]
        existing_run_id = str(github_outputs[0].get("run_id") or "") if github_outputs else ""
        published = {
            (str(row.get("title") or "").strip(), str(row.get("platform") or "").strip(), int(row.get("content_part") or 1))
            for row in publications
        }
        publishable = [row for row in (github_outputs or outputs) if str(row.get("content_kind") or "") == "en-zh"]
        targets = list(DEFAULT_PRODUCTION_CONFIG["publish_targets"])
        pending = [
            target for target in targets
            if any((str(row.get("title") or "").strip(), target, int(row.get("content_part") or 1)) not in published for row in publishable)
        ]
        expected = [
            {"learning_mode": mode, "video_format": video_format, "content_part": part}
            for mode in DEFAULT_PRODUCTION_CONFIG["learning_modes"]
            for video_format in DEFAULT_PRODUCTION_CONFIG["video_formats"]
            for part in range(1, (WORDS_PER_TASK + WORDS_PER_VIDEO - 1) // WORDS_PER_VIDEO + 1 if video_format == "standard" else 2)
        ]
        existing_parts = {(str(row.get("content_kind") or ""), int(row.get("content_part") or 1)) for row in outputs}
        pending_outputs = [item for item in expected if (video_content_kind(item["learning_mode"], item["video_format"]), item["content_part"]) not in existing_parts]
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
