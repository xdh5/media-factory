"""通过 stdio 调用项目 MCP，不直接访问 MCP 内部实现。"""

from __future__ import annotations

import asyncio
import json
import os
import sys
from contextlib import AsyncExitStack
from datetime import timedelta
from pathlib import Path

from mcp import ClientSession, StdioServerParameters
from mcp.client.stdio import stdio_client


class MCPCallError(RuntimeError):
    """MCP Tool 返回错误。"""


class ProjectMCP:
    def __init__(self, module: str, project_root: Path):
        self.module = module
        self.project_root = project_root
        self._stack = AsyncExitStack()
        self._session: ClientSession | None = None

    async def __aenter__(self) -> "ProjectMCP":
        environment = dict(os.environ)
        environment["PYTHONPATH"] = str(self.project_root)
        parameters = StdioServerParameters(
            command=sys.executable,
            args=["-m", self.module],
            env=environment,
            cwd=self.project_root,
        )
        read_stream, write_stream = await self._stack.enter_async_context(stdio_client(parameters))
        self._session = await self._stack.enter_async_context(ClientSession(read_stream, write_stream))
        await self._session.initialize()
        return self

    async def __aexit__(self, exc_type, exc, traceback) -> None:
        await self._stack.aclose()

    async def call(self, name: str, arguments: dict | None = None) -> dict:
        if self._session is None:
            raise RuntimeError("MCP 会话尚未初始化")
        if "poll_task" not in name:
            print(f"[MCP] 调用 {name}", flush=True)
        result = await self._session.call_tool(
            name,
            arguments or {},
            read_timeout_seconds=timedelta(minutes=3),
        )
        texts = [getattr(item, "text", "") for item in result.content if getattr(item, "type", "") == "text"]
        raw = "\n".join(text for text in texts if text).strip()
        if result.isError:
            raise MCPCallError(f"{name} 失败：{raw or 'MCP 未返回错误详情'}")
        structured = getattr(result, "structuredContent", None)
        if isinstance(structured, dict):
            return structured
        try:
            payload = json.loads(raw)
        except json.JSONDecodeError as exc:
            raise MCPCallError(f"{name} 返回的不是 JSON：{raw[:500]}") from exc
        if not isinstance(payload, dict):
            raise MCPCallError(f"{name} 必须返回 JSON 对象")
        return payload

    async def poll(self, tool_name: str, task_path: str, *, interval_seconds: int = 15) -> dict:
        round_id = 0
        while True:
            round_id += 1
            result = await self.call(tool_name, {"task_path": task_path})
            status = str(result.get("status") or "unknown")
            step = str(result.get("step") or "")
            task_id = str(result.get("task_id") or "")
            elapsed = float(result.get("duration_seconds") or 0)
            progress = str(result.get("progress") or "").strip()
            detail = progress or "后台线程仍在跑，这一步还没写下一级进度"
            print(
                f"[轮询 #{round_id}] {tool_name} task={task_id} step={step} "
                f"status={status} 已运行{elapsed:.0f}s | {detail}",
                flush=True,
            )
            if result.get("done") is True:
                if result.get("status") != "succeeded":
                    error = result.get("error")
                    print(
                        f"[轮询失败] {tool_name} task={task_id} step={step} "
                        f"{json.dumps(error, ensure_ascii=False, default=str)}",
                        flush=True,
                    )
                    raise MCPCallError(
                        f"后台任务失败：{json.dumps(error, ensure_ascii=False, default=str)}"
                    )
                payload = result.get("result")
                if not isinstance(payload, dict):
                    raise MCPCallError("后台任务成功但缺少 result 对象")
                print(
                    f"[轮询完成] {tool_name} task={task_id} step={step} 总耗时{elapsed}s",
                    flush=True,
                )
                return payload
            await asyncio.sleep(interval_seconds)
