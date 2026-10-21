"""复用项目 stdio 客户端，动态发现业务工具和服务说明。"""

from contextlib import AsyncExitStack

from core.mcp.client import ProjectMCP
from .settings import ROOT, SERVERS

# 只列经业务代码确认无写入的查询，选稿等 get 工具仍需审批。
READ_ONLY = {
    "finance_get_production_config", "finance_get_source_stats",
    "finance_list_source_authors", "finance_list_editorial_drafts",
    "finance_poll_task", "language_learning_get_production_config",
    "language_learning_poll_task", "anime_get_production_config",
    "anime_poll_task", "publishing_list_account_groups",
    "publishing_preview", "publishing_poll_task",
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
        return [{"type": "function", "function": {
            "name": tool.name, "description": tool.description or "",
            "parameters": tool.inputSchema,
        }} for _, tool in self.tools.values()]

    def read_only(self, name):
        return name in READ_ONLY

    def schema(self, name):
        return self.tools[name][1].inputSchema

    async def call(self, name, arguments, timeout):
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
