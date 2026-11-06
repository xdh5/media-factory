"""财经稿件和生产计划编排。"""
from __future__ import annotations
from copy import deepcopy
from ..infrastructure.gateways import get_source_script_stats, list_production_outputs, reserve_source_script
from ..infrastructure.gateways import get_topic
from ..config.settings import AUTOMATION_DAILY_OUTPUT_COUNT, DEFAULT_PRODUCTION_CONFIG, MCP_ID, SOURCE_COLLECTION_CODE, SOURCE_RESERVATION_MINUTES, TOPIC_DEDUPLICATION_DAYS, normalize_publish_date
from ..errors import WorkflowStepError
from ..services.save_draft import save_draft
from .common import _map_error
from ..services.editorial import list_editorial_drafts

def finance_get_production_config() -> dict:
    """返回财经生产唯一标准配置，供 Agent 与 GitHub Runner 共用。"""
    return deepcopy(DEFAULT_PRODUCTION_CONFIG)


def finance_get_automation_plan(publish_date: str) -> dict:
    """按计划发布日期返回 GitHub 财经待生产分片；每天目标数量由 MCP 统一维护。"""
    try:
        normalized_date = normalize_publish_date(publish_date)
        records = list_production_outputs(publish_date=normalized_date, business_line=MCP_ID)
        existing_parts = {
            int(item.get("content_part") or 1)
            for item in records
            if 1 <= int(item.get("content_part") or 1) <= AUTOMATION_DAILY_OUTPUT_COUNT
        }
        pending_parts = [
            part
            for part in range(1, AUTOMATION_DAILY_OUTPUT_COUNT + 1)
            if part not in existing_parts
        ]
        return {
            "publish_date": normalized_date,
            "should_generate": bool(pending_parts),
            "output_count": len(records),
            "desired_output_count": AUTOMATION_DAILY_OUTPUT_COUNT,
            "pending_content_parts": pending_parts,
            "skip_reason": "" if pending_parts else f"该计划发布日期已有 {len(existing_parts)} 条财经成片记录，已达到每日目标",
        }
    except Exception as exc:
        raise _map_error(exc) from exc


def finance_get_source_stats() -> dict:
    """只读统计财经数据库原稿总数、可用数、占用数和已使用数，不占用稿件。"""
    try:
        return get_source_script_stats(
            collection_code=SOURCE_COLLECTION_CODE,
            workflow=MCP_ID,
            reservation_minutes=SOURCE_RESERVATION_MINUTES,
        )
    except Exception as exc:
        raise _map_error(exc) from exc


def finance_get_production_outputs(publish_date: str) -> dict:
    """查询某个北京时间计划发布日期的财经成片。"""
    try:
        return {
            "publish_date": publish_date,
            "business_line": MCP_ID,
            "records": list_production_outputs(
                publish_date=publish_date,
                business_line=MCP_ID,
            ),
        }
    except Exception as exc:
        raise _map_error(exc) from exc


def finance_get_source_script() -> dict:
    """从已收集的财经文案中选择并临时占用一条未使用的稿件。"""
    try:
        return reserve_source_script(
            collection_code=SOURCE_COLLECTION_CODE,
            workflow=MCP_ID,
            reservation_minutes=SOURCE_RESERVATION_MINUTES,
        )
    except Exception as exc:
        raise _map_error(exc) from exc


def finance_get_topics() -> dict:
    """返回最近 30 天已占用话题。"""
    try:
        recent = get_topic(MCP_ID, TOPIC_DEDUPLICATION_DAYS)
        return {
            "workflow": MCP_ID,
            "deduplication_days": TOPIC_DEDUPLICATION_DAYS,
            "recent_topics": [item["topic"] for item in recent],
        }
    except Exception as exc:
        raise _map_error(exc) from exc


def finance_save_draft(
    topic: str,
    article: str,
    title: str,
    short_title: str,
    hashtags: list[str],
    cover_lines: list[str],
    source_aweme_id: str,
    source_reservation_token: str,
    source_hook: str,
    publish_date: str,
    cover_highlights: list[str] | None = None,
    content_part: int = 1,
    db_source_hook: str = "",
) -> dict:
    """保存完成两类必做改动与措辞级改写的稿件，来源稿件继续保持临时占用。

    同一天制作第二条时传 content_part=2：缓存与产物目录独立（run-YYYYMMDD-part2），
    D1 落库使用 content_part 区分，run_id 仍为 run-YYYYMMDD。
    db_source_hook：数据库原稿开头未经改动的逐字钩子（mark_used 校验用）；
    处理后的 source_hook 含品牌替换时与原稿不同，必须另外传原样钩子。不改错别字或标点。
    """
    try:
        stored = next((row["editorial"] for row in list_editorial_drafts(False)["records"]
                       if row["aweme_id"] == source_aweme_id), None)
        incoming = {"topic": topic, "article": article, "title": title, "short_title": short_title,
                    "hashtags": hashtags, "cover_lines": cover_lines, "cover_highlights": cover_highlights,
                    "source_hook": source_hook, "db_source_hook": db_source_hook}
        if stored is None or any(stored.get(key) != value for key, value in incoming.items()):
            raise WorkflowStepError("生产内容必须与稿库定稿一致，请先完成宿主定稿")
        clean_topic = str(topic or "").strip()
        recent = get_topic(MCP_ID, TOPIC_DEDUPLICATION_DAYS)
        if clean_topic.casefold() in {
            str(item.get("topic") or "").strip().casefold() for item in recent
        }:
            raise WorkflowStepError(
                f"话题最近 {TOPIC_DEDUPLICATION_DAYS} 天已经发布：{clean_topic}"
            )
        draft = save_draft(
            topic,
            article,
            title,
            short_title,
            hashtags,
            cover_lines,
            source_aweme_id,
            source_reservation_token,
            source_hook,
            publish_date,
            cover_highlights,
            content_part,
            db_source_hook,
        )
        return draft
    except Exception as exc:
        raise _map_error(exc) from exc
