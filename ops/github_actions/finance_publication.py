"""财经 GitHub 成片通过统一发布 MCP 预约到 YouTube。"""

from core.tools.media_records import list_production_outputs

from ._dates import resolve_publish_date
from ._mcp import ProjectMCP
from ._shared import PROJECT_ROOT


async def schedule_publication(publish_date: str) -> dict:
    """复用已交付成片，按公共财经排期补齐目标频道的预约记录。"""
    publish_date = resolve_publish_date(publish_date, 0)
    outputs = list_production_outputs(business_line="finance", publish_date=publish_date)
    if not any(row.get("source") == "github_workflow" and row.get("r2_url") for row in outputs):
        return {"skipped": True, "reason": "该日期没有已交付 R2 的 GitHub 财经成片"}
    request = {
        "business_line": "finance",
        "publish_date": publish_date,
        "account_group": "finance",
        "platforms": ["youtube"],
        "content_kind": "finance",
    }
    async with ProjectMCP("core.mcp.publishing", PROJECT_ROOT) as mcp:
        preview = await mcp.call("publishing_preview", request)
        if not preview["publishable_count"]:
            return {"skipped": True, "reason": "该日期的财经成片已在目标频道发布或预约"}
        if not preview["default_publication_plan"]:
            raise RuntimeError("该日期已无可用的财经预约时段，请手动指定未来时间或立即发布")
        started = await mcp.call("publishing_start_publish", request)
        return await mcp.poll("publishing_poll_task", started["task_path"])
