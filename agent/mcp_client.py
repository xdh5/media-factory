"""复用项目 stdio 客户端，动态发现业务工具和服务说明。"""

from contextlib import AsyncExitStack
from copy import deepcopy
import asyncio
import json

from langchain_core.tools import StructuredTool, ToolException
from langgraph.config import get_stream_writer

from .streaming import tool_event

from core.mcp.client import ProjectMCP
from .settings import ROOT, SERVERS

# 只列经业务代码确认无写入的查询，用于重试和回执去重。
READ_ONLY = {
    "finance_get_video_editorial_input", "finance_get_production_config", "finance_get_source_stats",
    "finance_list_source_authors", "finance_list_editorial_drafts",
    "finance_poll_task", "language_learning_get_production_config",
    "language_learning_poll_task", "anime_get_production_config",
    "anime_poll_task", "publishing_list_account_groups",
    "publishing_preview", "publishing_poll_task", "publishing_batch_status",
}


class MCPTools:
    def __init__(self, servers: list[str], session_timeout: float = 180):
        self.servers = servers
        self.stack = AsyncExitStack()
        self.tools = {}
        self.instructions = []
        self.session_timeout = session_timeout

    async def __aenter__(self):
        try:
            for name in self.servers:
                client = await self.stack.enter_async_context(ProjectMCP(
                    SERVERS[name], ROOT, session_timeout_seconds=self.session_timeout,
                    environment_overrides={"DASHSCOPE_BUSINESS_LINE": name} if name in {"finance", "language_learning"} else None))
                self.instructions.append(await client.instructions())
                for tool in await client.list_tools():
                    if tool.name in self.tools:
                        raise ValueError(f"MCP 工具名称重复：{tool.name}")
                    self.tools[tool.name] = (client, tool)
            return self
        except BaseException:
            await self.stack.aclose()
            raise

    async def __aexit__(self, *args):
        await self.stack.aclose()

    def definitions(self):
        definitions = [{"type": "function", "function": {
            "name": tool.name, "description": tool.description or "",
            "parameters": tool.inputSchema,
        }} for _, tool in self.tools.values()]
        for definition in definitions:
            if definition["function"]["name"] == "finance_submit_copy_reviews":
                schema = deepcopy(definition["function"]["parameters"])
                schema["properties"]["response_text"] = {
                    "type": "object", "description": "审核对象，直接提供 reviews 数组，无需编码成 JSON 字符串",
                    "properties": {"reviews": {"type": "array", "minItems": 1, "items": {
                        "type": "object", "properties": {"aweme_id": {"type": "string"},
                            "kind": {"type": "string", "enum": ["normal", "ad"]},
                            "text": {"type": "string"}, "reason": {"type": "string"},
                            "ad_segments": {"type": "array", "items": {"type": "string"}},
                            "editorial": {"type": "object"}},
                        "required": ["aweme_id", "kind", "text", "reason"]}}},
                    "required": ["reviews"],
                }
                definition["function"]["parameters"] = schema
        return definitions

    def instructions_for(self, names):
        return [instructions for server, instructions in zip(self.servers, self.instructions)
                if any(name.startswith(server + "_") for name in names)]

    def read_only(self, name):
        return name in READ_ONLY

    def schema(self, name):
        return next(item["function"]["parameters"] for item in self.definitions() if item["function"]["name"] == name)

    async def call(self, name, arguments, timeout):
        if name == "finance_submit_copy_reviews" and isinstance(arguments.get("response_text"), dict):
            arguments = {**arguments, "response_text": json.dumps(arguments["response_text"], ensure_ascii=False)}
        return await self.tools[name][0].call(name, arguments, read_timeout_seconds=timeout)

    def scoped(self, servers):
        return ScopedTools(self, servers)


class ScopedTools:
    """仅向模型暴露当前业务及统一发布，底层 MCP 会话继续共享。"""
    def __init__(self, parent, servers):
        self.parent = parent
        self.names = {name for name in parent.tools if any(name.startswith(server + "_") for server in servers)}
        self.instructions = [instructions for server, instructions in zip(parent.servers, parent.instructions) if server in servers]

    def definitions(self):
        return [definition for definition in self.parent.definitions() if definition["function"]["name"] in self.names]

    def instructions_for(self, names):
        return self.parent.instructions_for(names)

    def schema(self, name):
        if name not in self.names:
            raise KeyError(name)
        return self.parent.schema(name)

    def read_only(self, name):
        return self.parent.read_only(name)

    async def call(self, name, arguments, timeout):
        if name not in self.names:
            raise KeyError(name)
        return await self.parent.call(name, arguments, timeout)


def adapt_mcp_tool(definition, mcp_tools, settings):
    """将 MCP JSON Schema 与异步调用注册为可执行的 LangChain 工具。"""
    function = definition["function"]
    name = function["name"]

    async def invoke(**arguments):
        result = await asyncio.wait_for(
            mcp_tools.call(name, arguments, settings.tool_timeout), settings.tool_timeout)
        # 后台轮询在工具内部等待，避免为每次进度查询请求模型。
        while (name.endswith("_poll_task") and isinstance(result, dict)
               and result.get("done") is False and not result.get("error")
               and result.get("status") not in {"failed", "cancelled"}):
            get_stream_writer()(tool_event(name, result))
            await asyncio.sleep(15)
            result = await asyncio.wait_for(
                mcp_tools.call(name, arguments, settings.tool_timeout), settings.tool_timeout)
        if isinstance(result, dict) and (result.get("error") or result.get("status") == "failed"):
            raise ToolException(json.dumps(result, ensure_ascii=False))
        payload = result.get("result", result) if isinstance(result, dict) else {}
        covers = [item["cover"] for item in payload.get("evidence", []) if item.get("cover")] if isinstance(payload, dict) else []
        if covers:
            return [{"type": "text", "text": json.dumps(result, ensure_ascii=False)},
                    *[{"type": "image_url", "image_url": {"url": cover["image_url"]}} for cover in covers]]
        return result

    return StructuredTool.from_function(name=name, description=function["description"],
        args_schema=function["parameters"], coroutine=invoke)

