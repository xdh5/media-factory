"""财经稿件和生产计划编排。"""
from __future__ import annotations

from workflows.finance.infrastructure.scripts import get_source_script_stats
from tools.database.production_records import list_production_outputs
from workflows.finance.tools.drafts import finance_get_automation_plan
from tools.database.topic_history import list_recent_topics as get_topic
from workflows.finance.parameters import MCP_ID, SOURCE_COLLECTION_CODE, SOURCE_RESERVATION_MINUTES, TOPIC_DEDUPLICATION_DAYS
from workflows.finance.tools.drafts import save_draft
from .common import _map_error



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
