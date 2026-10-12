"""语言学习 MCP 注册与服务实例。"""

from mcp.server.fastmcp import FastMCP

from .config import SERVER_INSTRUCTIONS, SERVER_NAME
from .tools import register_tools


def create_server() -> FastMCP:
    """创建并注册语言学习 MCP。"""
    server = FastMCP(SERVER_NAME, instructions=SERVER_INSTRUCTIONS)
    register_tools(server)
    return server


mcp = create_server()

__all__ = ["create_server", "mcp"]
