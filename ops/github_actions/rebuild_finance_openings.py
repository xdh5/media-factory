"""通过财经 MCP 重制已有成片首幕；不调用模型、不发布。"""

import argparse
import asyncio
import json
import os
from pathlib import Path

from ._mcp import ProjectMCP
from ._shared import PROJECT_ROOT


async def main(publish_date: str):
    title_lines = json.loads(os.environ.get("HOOK_TITLE_LINES", "{}"))
    run_id = "run-" + publish_date.replace("-", "")
    parts = {str(part): title_lines[key] for part in (1, 2)
             if (key := run_id + (f"-part{part}" if part > 1 else "")) in title_lines}
    async with ProjectMCP("core.mcp.finance", PROJECT_ROOT) as client:
        config = await client.call("finance_get_production_config")
        started = await client.call("finance_start_rebuild_openings", {
            "publish_date": publish_date, "title_lines_by_part": parts,
            "production_config": config["production_config"], "video_config": config["video_config"],
        })
        result = await client.poll("finance_poll_task", started["task_path"])
    output = PROJECT_ROOT / "cache" / "finance-rebuild-results" / f"{publish_date}.json"
    output.parent.mkdir(parents=True, exist_ok=True)
    output.write_text(json.dumps(result, ensure_ascii=False, indent=2), encoding="utf-8")
    print(json.dumps(result, ensure_ascii=False), flush=True)


if __name__ == "__main__":
    parser = argparse.ArgumentParser()
    parser.add_argument("--publish-date", required=True)
    asyncio.run(main(parser.parse_args().publish_date))
