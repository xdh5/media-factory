"""在 Docker 中调用动漫 MCP，并等待后台任务结束。"""

import argparse
import asyncio
import json
import os
import sys
from pathlib import Path

from mcp import ClientSession, StdioServerParameters
from mcp.client.stdio import stdio_client
from dotenv import load_dotenv


def payload(result):
    if result.isError:
        raise RuntimeError(str(result.content))
    if result.structuredContent:
        return result.structuredContent
    return json.loads(next(item.text for item in result.content if item.type == "text"))


async def main():
    parser = argparse.ArgumentParser(description="调用动漫 MCP 后台工具")
    parser.add_argument("--tool", required=True)
    parser.add_argument("--arguments-file", required=True, type=Path)
    parser.add_argument("--result-file", required=True, type=Path)
    args = parser.parse_args()
    parameters = json.loads(args.arguments_file.read_text(encoding="utf-8-sig"))
    root = Path(__file__).resolve().parents[2]
    load_dotenv(root / ".env")
    environment = dict(os.environ)
    # 宿主机绝对路径不能直接在容器内读取；优先使用同一工作区挂载的凭据文件。
    credential_file = root / "integrations/media-publisher/data/credentials.json"
    if Path("/.dockerenv").exists() and credential_file.is_file():
        environment["PUBLISHING_CREDENTIALS_FILE"] = str(credential_file)
    server = StdioServerParameters(command=sys.executable, args=["-m", "core.mcp.anime"], env=environment)
    async with stdio_client(server) as (reader, writer):
        async with ClientSession(reader, writer) as session:
            await session.initialize()
            started = payload(await session.call_tool(args.tool, parameters))
            if "task_path" not in started:
                args.result_file.parent.mkdir(parents=True, exist_ok=True)
                args.result_file.write_text(json.dumps(started, ensure_ascii=False, indent=2), encoding="utf-8")
                print(f"工具完成：{args.result_file}", flush=True)
                return
            previous = None
            while True:
                result = payload(await session.call_tool("anime_poll_task", {"task_path": started["task_path"]}))
                if result.get("progress") != previous:
                    previous = result.get("progress")
                    if previous:
                        print(previous, flush=True)
                if result["done"]:
                    args.result_file.write_text(json.dumps(result, ensure_ascii=False, indent=2), encoding="utf-8")
                    if result["status"] != "succeeded":
                        raise RuntimeError(str(result.get("error")))
                    print(f"任务完成：{args.result_file}", flush=True)
                    return
                await asyncio.sleep(5)


if __name__ == "__main__":
    asyncio.run(main())
