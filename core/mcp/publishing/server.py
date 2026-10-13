"""统一发布 MCP 注册与服务实例。"""

import warnings

from mcp.server.fastmcp import FastMCP

from .config import SERVER_INSTRUCTIONS, SERVER_NAME
from .tools import register_tools

warnings.filterwarnings("ignore", message=r"Field 'lifespan' has an incomplete definition.*")


def create_server() -> FastMCP:
    """创建并注册统一发布 MCP。"""
    server = FastMCP(SERVER_NAME, instructions=SERVER_INSTRUCTIONS)
    register_tools(server)
    return server


mcp = create_server()

__all__ = ["create_server", "mcp"]
