"""把财经工作流注册为 MCP 工具。"""

from mcp.server.fastmcp import FastMCP
from ..workflows import ALL_TOOLS

def register_tools(server: FastMCP) -> None:
    """按稳定顺序注册全部财经工具。"""
    for handler in ALL_TOOLS:
        server.tool()(handler)
