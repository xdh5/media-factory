"""财经 MCP 注册与服务实例。"""

import os
import warnings

os.environ.setdefault("DASHSCOPE_BUSINESS_LINE", "finance")
warnings.filterwarnings("ignore", message=r"Field 'lifespan' has an incomplete definition.*")

from mcp.server.fastmcp import FastMCP
from .config.server import SERVER_NAME, SERVER_INSTRUCTIONS
from .tools import register_tools

def create_server() -> FastMCP:
    """创建并注册财经 MCP。"""
    server = FastMCP(SERVER_NAME, instructions=SERVER_INSTRUCTIONS)
    register_tools(server)
    return server

mcp = create_server()
