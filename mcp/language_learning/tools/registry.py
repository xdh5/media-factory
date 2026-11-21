"""把语言学习工作流注册为 MCP Tools。"""

from mcp.server.fastmcp import FastMCP

from ..workflows import ALL_TOOLS


def register_tools(server: FastMCP) -> None:
    """按稳定顺序注册全部语言学习工具。"""
    for handler in ALL_TOOLS:
        server.tool()(handler)
