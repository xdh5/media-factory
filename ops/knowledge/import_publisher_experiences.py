"""通过标准 MCP 幂等导入已有业务回执验证的发布经验。"""

import asyncio
import json
from pathlib import Path

from media_factory_mcp.client import ProjectMCP


async def main() -> None:
    """原文保存与索引可见分别报告，不自动无限等待。"""
    root = Path(__file__).resolve().parents[2]
    items = json.loads(Path(__file__).with_name("publisher-experiences.json").read_text(encoding="utf-8"))
    async with ProjectMCP("media_factory_mcp.knowledge", root) as client:
        result = await client.call("knowledge_register_base", {
            "knowledge_base": "publisher-errors", "kind": "publisher-errors", "profile_name": "publisher-default",
        })
        if not result["ok"]:
            raise RuntimeError(json.dumps(result, ensure_ascii=False))
        for item in items:
            result = await client.call("knowledge_add", {"knowledge_base": "publisher-errors", **item})
            if not result["ok"]:
                raise RuntimeError(json.dumps(result, ensure_ascii=False))
            print(json.dumps({"标题": item["title"], "文档": result["document"]["id"], "重复": result["duplicate"]}, ensure_ascii=False))
        result = await client.call("knowledge_sync", {"knowledge_base": "publisher-errors", "limit": 5})
        print(json.dumps(result, ensure_ascii=False))


if __name__ == "__main__":
    asyncio.run(main())
